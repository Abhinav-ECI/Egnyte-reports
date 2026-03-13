import argparse
import requests
from urllib.parse import quote
from typing import Optional


def load_config(file_path: str) -> dict:
    config = {}
    with open(file_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            config[key.strip().upper()] = value.strip()
    return config

def to_gb(num_bytes: int) -> float:
    return round(num_bytes / (1024 ** 3), 3)


def normalize_folder_path(raw_path: str) -> str:
    path = (raw_path or "").strip().replace("\\", "/")

    # Support drive-based mapped paths like Z:/Shared/Team/Folder.
    if len(path) >= 2 and path[1] == ":":
        path = path[2:]

    if not path.startswith("/"):
        path = "/" + path

    while "//" in path:
        path = path.replace("//", "/")

    return path

def get_folder_id(domain: str, token: str, folder_path: str) -> str:
    encoded = quote(folder_path, safe="/")
    url = f"https://{domain}/pubapi/v1/fs{encoded}"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if "folder_id" not in data:
        raise RuntimeError(f"Could not resolve folder_id for path: {folder_path}")
    return data["folder_id"]

def get_folder_stats(domain: str, token: str, folder_id: str) -> dict:
    url = f"https://{domain}/pubapi/v1/fs/ids/folder/{folder_id}/stats"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.json()


def build_report_text(folder_path: str, stats: dict) -> str:
    files_b = int(stats.get("allFilesSize", 0))
    file_count = int(stats.get("filesCount", 0))
    folder_count = int(stats.get("foldersCount", 0))

    return (
        f"Folder Path: {folder_path}\n"
        f"Files Total Size (B): {files_b}\n"
        f"Files Total Size (GB): {to_gb(files_b):.3f}\n"
        f"File Count: {file_count}\n"
        f"Folder Count: {folder_count}"
    )


def generate_report(domain: str, token: str, raw_folder_path: str) -> str:
    folder_path = normalize_folder_path(raw_folder_path)
    folder_id = get_folder_id(domain, token, folder_path)
    stats = get_folder_stats(domain, token, folder_id)
    return build_report_text(folder_path, stats)


def _is_streamlit_runtime() -> bool:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        return get_script_run_ctx() is not None
    except Exception:
        return False


def run_streamlit_app(config_path: str = "egnyte_secrets.txt") -> None:
    import streamlit as st

    config = {}
    try:
        config = load_config(config_path)
    except FileNotFoundError:
        # Keep working with manual inputs in Streamlit.
        config = {}

    st.set_page_config(page_title="Egnyte Folder Report", layout="centered")
    st.title("Egnyte Folder Report")

    domain = st.text_input("Domain", value=config.get("DOMAIN", ""))
    token = st.text_input("OAuth Token", value=config.get("TOKEN", ""), type="password")
    folder_path = st.text_input("Folder Path", value="")

    if st.button("Generate Report", type="primary"):
        missing = []
        if not domain.strip():
            missing.append("DOMAIN")
        if not token.strip():
            missing.append("TOKEN")
        if not folder_path.strip():
            missing.append("FOLDER PATH")

        if missing:
            st.error("Missing required values: " + ", ".join(missing))
            return

        try:
            report = generate_report(domain.strip(), token.strip(), folder_path)
            st.success("Report generated")
            st.text_area("Report", value=report, height=220)
            st.download_button(
                "Download Report",
                data=report,
                file_name="egnyte_report.txt",
                mime="text/plain",
            )
        except requests.HTTPError as e:
            st.error(f"HTTP error: {e.response.status_code} {e.response.text}")
        except Exception as e:
            st.error(f"Error: {e}")


def create_main_window(domain: str, token: str, default_path: str = "") -> None:
    import tkinter as tk
    from tkinter import messagebox

    default_path = normalize_folder_path(default_path) if default_path else ""

    root = tk.Tk()
    root.title("Egnyte Folder Report")
    root.geometry("760x360")
    root.minsize(700, 320)

    input_frame = tk.Frame(root)
    input_frame.pack(fill="x", padx=12, pady=(12, 8))

    tk.Label(input_frame, text="Folder Path:").grid(row=0, column=0, sticky="w", padx=(0, 8))

    folder_var = tk.StringVar(value=default_path)
    folder_entry = tk.Entry(input_frame, textvariable=folder_var)
    folder_entry.grid(row=0, column=1, sticky="ew")
    input_frame.grid_columnconfigure(1, weight=1)

    result_text = tk.Text(root, wrap="word", height=12)
    result_text.pack(fill="both", expand=True, padx=12, pady=(0, 8))

    status_var = tk.StringVar(value="Ready")

    def set_result(text: str) -> None:
        result_text.config(state="normal")
        result_text.delete("1.0", "end")
        result_text.insert("1.0", text)
        result_text.config(state="disabled")

    def on_generate() -> None:
        raw_folder_path = folder_var.get().strip()
        if not raw_folder_path:
            messagebox.showerror("Input Error", "Folder path cannot be empty.", parent=root)
            return

        folder_path = normalize_folder_path(raw_folder_path)
        folder_var.set(folder_path)

        status_var.set("Generating report...")
        root.update_idletasks()

        try:
            set_result(generate_report(domain, token, folder_path))
            status_var.set("Report generated")
        except requests.HTTPError as e:
            status_var.set("Error")
            messagebox.showerror(
                "HTTP Error",
                f"{e.response.status_code} {e.response.text}",
                parent=root,
            )
        except Exception as e:
            status_var.set("Error")
            messagebox.showerror("Error", str(e), parent=root)

    generate_button = tk.Button(input_frame, text="Generate Report", width=16, command=on_generate)
    generate_button.grid(row=0, column=2, padx=(8, 0))

    bottom_frame = tk.Frame(root)
    bottom_frame.pack(fill="x", padx=12, pady=(0, 12))

    def copy_to_clipboard() -> None:
        text = result_text.get("1.0", "end-1c").strip()
        if not text:
            return
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        status_var.set("Copied report to clipboard")

    copy_button = tk.Button(bottom_frame, text="Copy", width=12, command=copy_to_clipboard)
    copy_button.pack(side="left")

    status_label = tk.Label(bottom_frame, textvariable=status_var, anchor="w")
    status_label.pack(side="left", padx=(10, 0))

    if default_path:
        on_generate()

    folder_entry.focus_set()
    root.mainloop()

def main(argv: Optional[list[str]] = None):
    if _is_streamlit_runtime():
        run_streamlit_app()
        return

    parser = argparse.ArgumentParser(description="Fetch Egnyte folder statistics and print to terminal.")
    parser.add_argument("--config", default="egnyte_secrets.txt", help="Path to config txt file")
    parser.add_argument("--domain", help="Egnyte domain, e.g. company.egnyte.com")
    parser.add_argument("--token", help="OAuth bearer token")
    parser.add_argument("--path", help="Folder path, e.g. /Shared/Shared/SPP/KPMG/Projects")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)

        domain = args.domain or config.get("DOMAIN")
        token = args.token or config.get("TOKEN")
        default_path = args.path or ""

        missing = []
        if not domain:
            missing.append("DOMAIN")
        if not token:
            missing.append("TOKEN")

        if missing:
            raise RuntimeError(
                "Missing required values: "
                + ", ".join(missing)
                + ". Set them in config file or pass CLI flags."
            )

        create_main_window(domain, token, default_path)
    except requests.HTTPError as e:
        print(f"HTTP error: {e.response.status_code} {e.response.text}")
    except FileNotFoundError:
        print(
            f"Config file not found: {args.config}. Create it with DOMAIN and TOKEN values."
        )
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()