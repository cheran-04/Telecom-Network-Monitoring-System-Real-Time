# streamlit_app.py
import streamlit as st
import pandas as pd
import time
import threading
import json
import queue
import websocket  # from websocket-client
import os

# internal Docker name for backend service
BACKEND_WS = os.environ.get("BACKEND_WS", "ws://backend:8000/ws/metrics")
API_BASE = os.environ.get("API_BASE", "http://backend:8000/api")

st.set_page_config(page_title="Telecom Monitor (WebSocket)", layout="wide")

if "df" not in st.session_state:
    st.session_state.df = pd.DataFrame(columns=["id","device_id","latency","jitter","packet_loss","bandwidth","created_at"])

if "ws_queue" not in st.session_state:
    st.session_state.ws_queue = queue.Queue()

# websocket callbacks
def on_message(ws, message):
    try:
        msg = json.loads(message)
        st.session_state.ws_queue.put(msg)
    except Exception as e:
        # ignore bad messages
        print("ws on_message error:", e)

def on_error(ws, error):
    print("ws error:", error)

def on_close(ws, close_status_code, close_msg):
    print("ws closed", close_status_code, close_msg)

def on_open(ws):
    print("ws opened")

# thread to run websocket
def start_ws():
    # avoid multiple threads
    ws = websocket.WebSocketApp(BACKEND_WS,
                                on_open=on_open,
                                on_message=on_message,
                                on_error=on_error,
                                on_close=on_close)
    ws.run_forever()

# start ws thread once
if "ws_thread_started" not in st.session_state:
    t = threading.Thread(target=start_ws, daemon=True)
    t.start()
    st.session_state.ws_thread_started = True

st.title("📡 Telecom Network Monitoring — Real-Time (WebSocket)")

# process queue: consume all messages waiting
new_rows = 0
q = st.session_state.ws_queue
while not q.empty():
    msg = q.get_nowait()
    # expected format: {"event": "new_metric", "data": {...}}
    if msg.get("event") == "new_metric":
        data = msg.get("data", {})
        # ensure columns and one-row dict
        row = {
            "id": data.get("id"),
            "device_id": data.get("device_id"),
            "latency": data.get("latency"),
            "jitter": data.get("jitter"),
            "packet_loss": data.get("packet_loss"),
            "bandwidth": data.get("bandwidth"),
            "created_at": data.get("created_at")
        }
        st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([row])], ignore_index=True)
        new_rows += 1

# keep only recent N rows for performance
MAX_ROWS = 2000
if len(st.session_state.df) > MAX_ROWS:
    st.session_state.df = st.session_state.df.tail(MAX_ROWS).reset_index(drop=True)

# Display
if st.session_state.df.empty:
    st.info("Waiting for live metrics... start the simulator.")
else:
    st.session_state.df['created_at'] = pd.to_datetime(st.session_state.df['created_at'])
    latest = st.session_state.df.tail(100).sort_values("created_at")
    st.write("### Latest metrics (live feed)")
    st.dataframe(latest)

    # chart: latency and bandwidth
    chart_df = latest.set_index("created_at")[["latency","bandwidth"]]
    st.line_chart(chart_df)

# small status
st.write(f"Live rows received this run: {new_rows}")

# short sleep then rerun to update UI with new queue items continuously
time.sleep(0.8)
st.rerun()

