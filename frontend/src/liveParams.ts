/** Small live-mode configuration reader; no runtime or terminal imports. */
export interface LiveInitial {
  baseUrl: string;
  token: string;
  entry: string;
  ptyCommand: string;
  auto: boolean;
}

export function readLiveParams(): LiveInitial {
  const q = new URLSearchParams(window.location.search);
  return {
    baseUrl: q.get("broker") ?? sessionStorage.getItem("lectpy.broker") ?? "http://127.0.0.1:7888",
    token: q.get("token") ?? sessionStorage.getItem("lectpy.token") ?? "",
    entry: q.get("entry") ?? "examples/lecture_01.py",
    ptyCommand: q.get("ptycmd") ?? "python --version",
    auto: q.get("auto") !== "0",
  };
}
