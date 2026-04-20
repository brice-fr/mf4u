use tauri::Manager;
use tauri_plugin_shell::process::CommandEvent;
use tauri_plugin_shell::ShellExt;
use tokio::sync::Mutex;
use serde_json::{json, Value};

struct Sidecar {
    child: tauri_plugin_shell::process::CommandChild,
    rx: tokio::sync::mpsc::Receiver<CommandEvent>,
    next_id: u64,
}

// -------------------------------------------------------------------------- //
// Low-level JSON-RPC relay
// -------------------------------------------------------------------------- //

async fn rpc_call(
    sidecar: &Mutex<Sidecar>,
    method: &str,
    params: Value,
) -> Result<Value, String> {
    let mut s = sidecar.lock().await;
    let id = s.next_id;
    s.next_id += 1;

    let req = json!({ "jsonrpc": "2.0", "method": method, "params": params, "id": id });
    s.child
        .write(format!("{req}\n").as_bytes())
        .map_err(|e| e.to_string())?;

    loop {
        match s.rx.recv().await {
            Some(CommandEvent::Stdout(line)) => {
                let resp: Value =
                    serde_json::from_slice(&line).map_err(|e| e.to_string())?;
                if let Some(err) = resp.get("error") {
                    let msg = err["message"]
                        .as_str()
                        .unwrap_or("sidecar error")
                        .to_string();
                    return Err(msg);
                }
                return Ok(resp["result"].clone());
            }
            Some(CommandEvent::Stderr(line)) => {
                eprintln!("[sidecar] {}", String::from_utf8_lossy(&line));
            }
            Some(CommandEvent::Error(e)) => return Err(format!("sidecar error: {e}")),
            Some(CommandEvent::Terminated(p)) => {
                return Err(format!("sidecar exited (code {:?})", p.code))
            }
            None => return Err("sidecar channel closed".into()),
            _ => {}
        }
    }
}

// -------------------------------------------------------------------------- //
// Tauri commands
// -------------------------------------------------------------------------- //

#[tauri::command]
async fn ping(sidecar: tauri::State<'_, Mutex<Sidecar>>) -> Result<Value, String> {
    rpc_call(&sidecar, "ping", json!({})).await
}

#[tauri::command]
async fn open_file(
    path: String,
    sidecar: tauri::State<'_, Mutex<Sidecar>>,
) -> Result<Value, String> {
    rpc_call(&sidecar, "open_file", json!({ "path": path })).await
}

#[tauri::command]
async fn get_structure(
    session_id: String,
    sidecar: tauri::State<'_, Mutex<Sidecar>>,
) -> Result<Value, String> {
    rpc_call(&sidecar, "get_structure", json!({ "session_id": session_id })).await
}

#[tauri::command]
async fn get_signal_stats(
    session_id: String,
    group_index: u32,
    channel_name: String,
    sidecar: tauri::State<'_, Mutex<Sidecar>>,
) -> Result<Value, String> {
    rpc_call(
        &sidecar,
        "get_signal_stats",
        json!({
            "session_id":   session_id,
            "group_index":  group_index,
            "channel_name": channel_name,
        }),
    )
    .await
}

#[tauri::command]
async fn close_session(
    session_id: String,
    sidecar: tauri::State<'_, Mutex<Sidecar>>,
) -> Result<Value, String> {
    rpc_call(&sidecar, "close_session", json!({ "session_id": session_id })).await
}

#[tauri::command]
async fn start_export(
    session_id: String,
    format: String,
    output_path: String,
    db_assignments: Option<Value>,
    flatten: Option<bool>,
    sidecar: tauri::State<'_, Mutex<Sidecar>>,
) -> Result<Value, String> {
    rpc_call(
        &sidecar,
        "start_export",
        json!({
            "session_id":     session_id,
            "format":         format,
            "output_path":    output_path,
            "db_assignments": db_assignments,
            "flatten":        flatten.unwrap_or(false),
        }),
    )
    .await
}

#[tauri::command]
async fn preview_bus_decoding(
    session_id: String,
    db_assignments: Value,
    sidecar: tauri::State<'_, Mutex<Sidecar>>,
) -> Result<Value, String> {
    rpc_call(
        &sidecar,
        "preview_bus_decoding",
        json!({
            "session_id":     session_id,
            "db_assignments": db_assignments,
        }),
    )
    .await
}

#[tauri::command]
async fn get_export_progress(
    job_id: String,
    sidecar: tauri::State<'_, Mutex<Sidecar>>,
) -> Result<Value, String> {
    rpc_call(&sidecar, "get_export_progress", json!({ "job_id": job_id })).await
}

#[tauri::command]
async fn cancel_export(
    job_id: String,
    sidecar: tauri::State<'_, Mutex<Sidecar>>,
) -> Result<Value, String> {
    rpc_call(&sidecar, "cancel_export", json!({ "job_id": job_id })).await
}

// -------------------------------------------------------------------------- //
// App entry point
// -------------------------------------------------------------------------- //

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            let (rx, child) = app
                .shell()
                .sidecar("mf4u_sidecar")?
                .spawn()?;
            app.manage(Mutex::new(Sidecar { child, rx, next_id: 0 }));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            ping,
            open_file,
            get_structure,
            get_signal_stats,
            close_session,
            start_export,
            get_export_progress,
            cancel_export,
            preview_bus_decoding,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
