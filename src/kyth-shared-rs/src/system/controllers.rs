//! Port of `kyth_shared.system.controllers` — pure controller detection.
//! lsusb → vid/pid → PlayStation/Xbox/Nintendo + lsmod + /dev/input/by-id

use std::collections::HashMap;
use std::fs;
use std::path::Path;
use std::process::Command;

fn command_stdout(cmd: &str, args: &[&str], timeout_secs: u64) -> String {
    use std::process::Stdio;
    let mut child = match Command::new(cmd).args(args).stdout(Stdio::piped()).stderr(Stdio::piped()).spawn() {
        Ok(c) => c,
        Err(_) => return String::new(),
    };
    let start = std::time::Instant::now();
    let dur = std::time::Duration::from_secs(timeout_secs);
    loop {
        match child.try_wait() {
            Ok(Some(s)) => {
                let out = child.wait_with_output().unwrap_or_else(|_| std::process::Output { status: s, stdout: Vec::new(), stderr: Vec::new() });
                return String::from_utf8_lossy(&out.stdout).to_string();
            }
            Ok(None) => {
                if start.elapsed() > dur {
                    let _ = child.kill();
                    let _ = child.wait();
                    return String::new();
                }
                std::thread::sleep(std::time::Duration::from_millis(50));
            }
            Err(_) => return String::new(),
        }
    }
}

#[derive(Debug, Clone, serde::Serialize)]
pub struct ControllersDetect {
    pub usb_controllers: Vec<(String, String)>,
    pub input_nodes: Vec<String>,
    pub xone_dongle: bool,
    pub xone_loaded: bool,
    pub xpadneo_loaded: bool,
    pub hid_ps_loaded: bool,
    pub dualsense_found: bool,
}

pub fn detect_controllers() -> ControllersDetect {
    let usb_text = command_stdout("lsusb", &[], 6);
    let lsmod_text = command_stdout("lsmod", &[], 4);
    let mut usb_controllers = Vec::new();
    let mut xone_dongle = false;
    let mut dualsense_found = false;
    let mut ds4_found = false;
    let mut switch_pro_found = false;

    let gaming_vids: HashMap<&str, &str> = [
        ("045e", "Xbox"), ("054c", "PlayStation"), ("057e", "Nintendo"),
        ("2dc8", "8BitDo"), ("0f0d", "HORI"), ("28de", "Valve"),
        ("20d6", "PowerA"), ("0e6f", "PDP"),
    ].into();

    for line in usb_text.lines() {
        // ID 045e:02fe …
        if let Some(id_pos) = line.find("ID ") {
            let rest = &line[id_pos + 3..];
            if rest.len() >= 9 {
                let vid = rest[0..4].to_lowercase();
                let pid = rest[5..9].to_lowercase();
                let desc = rest[9..].trim().trim_start_matches(|c| c==' ' || c=='\t').trim().to_string();
                if let Some(_label) = gaming_vids.get(vid.as_str()) {
                    if vid == "045e" && ["02e6","02fe"].contains(&pid.as_str()) {
                        xone_dongle = true;
                        usb_controllers.push(("Xbox Wireless USB Dongle".to_string(), "xbox_dongle".to_string()));
                    } else if vid == "054c" && ["0ce6","0df2"].contains(&pid.as_str()) {
                        dualsense_found = true;
                        usb_controllers.push(("PlayStation 5 DualSense".to_string(), "dualsense".to_string()));
                    } else if vid == "054c" && ["05c4","09cc","0ba0"].contains(&pid.as_str()) {
                        ds4_found = true;
                        usb_controllers.push(("PlayStation 4 DualShock 4".to_string(), "ds4".to_string()));
                    } else if vid == "057e" && pid == "2009" {
                        switch_pro_found = true;
                        usb_controllers.push(("Nintendo Switch Pro Controller".to_string(), "switch_pro".to_string()));
                    } else {
                        let label = if desc.is_empty() { format!("{} controller", gaming_vids[&vid.as_str()]) } else { desc };
                        usb_controllers.push((label, "generic".to_string()));
                    }
                }
            }
        }
    }
    let _ = (ds4_found, switch_pro_found);
    let input_nodes = fs::read_dir("/dev/input/by-id").ok().map(|rd| {
        let mut v: Vec<String> = rd.filter_map(|e| e.ok()).map(|e| e.file_name().to_string_lossy().to_string()).filter(|n| {
            let l = n.to_lowercase();
            l.contains("joystick") || l.contains("gamepad") || l.contains("controller")
        }).collect();
        v.sort();
        v
    }).unwrap_or_default();

    // efivars SecureBoot check not needed for return value but mirrors Python's side read (ignored)
    let _secure_boot = fs::read_dir("/sys/firmware/efi/efivars").ok().and_then(|rd| {
        for e in rd.filter_map(|e| e.ok()) {
            let name = e.file_name().to_string_lossy().to_string();
            if name.starts_with("SecureBoot-") {
                if let Ok(data) = fs::read(e.path()) { return Some(data.len()>=5 && data[4]==1); }
            }
        }
        None
    }).unwrap_or(false);

    let modules = lsmod_text.to_lowercase().replace('-', "_");
    ControllersDetect {
        usb_controllers,
        input_nodes,
        xone_dongle,
        xone_loaded: modules.contains("xone_hid"),
        xpadneo_loaded: modules.contains("xpadneo"),
        hid_ps_loaded: modules.contains("hid_playstation"),
        dualsense_found,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn detect_returns_struct() {
        let d = detect_controllers();
        // Just verify it doesn't panic and fields are bool/vec
        let _ = d.xone_loaded;
        assert!(d.usb_controllers.len() <= 20);
    }
}
