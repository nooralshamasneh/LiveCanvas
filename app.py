import os
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
socketio = SocketIO(app, cors_allowed_origins="*")

MAX_STROKES_PER_ROOM = 3000
MAX_POINTS_PER_STROKE = 5000

boards = {} 
members = {}  


def clean_room(name):
    name = str(name or "").strip()[:40]
    return name or "default"


def clean_points(points):
    out = []
    for p in (points or [])[:MAX_POINTS_PER_STROKE]:
        out.append([float(p[0]), float(p[1])])
    return out


def clean_stroke(raw):
    try:
        return {
            "id": str(raw["id"])[:40],
            "uid": str(raw.get("uid", ""))[:20],
            "color": str(raw.get("color", "#000000"))[:9],
            "size": max(1.0, min(float(raw.get("size", 5)), 200.0)),
            "erase": bool(raw.get("erase", False)),
            "points": clean_points(raw.get("points", [])),
        }
    except (KeyError, TypeError, ValueError, IndexError, AttributeError):
        return None


def find_stroke(room, stroke_id):
    for s in reversed(boards.get(room, [])):
        if s["id"] == stroke_id:
            return s
    return None


def current_room():
    return members.get(request.sid)


def send_user_count(room):
    count = sum(1 for r in members.values() if r == room)
    emit("user_count", count, room=room)


def add_stroke(event_name, data):
    room = current_room()
    stroke = clean_stroke((data or {}).get("stroke") or {})
    if not room or not stroke:
        return
    board = boards.setdefault(room, [])
    board.append(stroke)
    if len(board) > MAX_STROKES_PER_ROOM:
        board.pop(0)
    emit(event_name, {"stroke": stroke}, room=room, include_self=False)


@app.route("/")
def index():
    return render_template("index.html")


@socketio.on("join_room")
def handle_join(data):
    room = clean_room((data or {}).get("room"))
    join_room(room)
    members[request.sid] = room
    # المنضم الجديد بياخد كل الرسم الموجود
    emit("init_board", boards.setdefault(room, []))
    send_user_count(room)


@socketio.on("stroke_start")
def handle_stroke_start(data):
    add_stroke("stroke_start", data)


@socketio.on("stroke_full")  # للـ Redo
def handle_stroke_full(data):
    add_stroke("stroke_full", data)


@socketio.on("stroke_point")
def handle_stroke_point(data):
    room = current_room()
    data = data or {}
    stroke = find_stroke(room, data.get("id")) if room else None
    point = data.get("point")
    if not stroke or not point or len(stroke["points"]) >= MAX_POINTS_PER_STROKE:
        return
    try:
        p = [float(point[0]), float(point[1])]
    except (TypeError, ValueError, IndexError):
        return
    stroke["points"].append(p)
    emit("stroke_point", {"id": stroke["id"], "point": p}, room=room, include_self=False)


@socketio.on("stroke_replace")  # لـ Fix Shape
def handle_stroke_replace(data):
    room = current_room()
    data = data or {}
    stroke = find_stroke(room, data.get("id")) if room else None
    if not stroke:
        return
    try:
        stroke["points"] = clean_points(data.get("points"))
    except (TypeError, ValueError, IndexError):
        return
    emit("stroke_replace", {"id": stroke["id"], "points": stroke["points"]},
         room=room, include_self=False)


@socketio.on("undo")
def handle_undo(data):
    room = current_room()
    stroke = find_stroke(room, (data or {}).get("id")) if room else None
    if stroke:
        boards[room].remove(stroke)
        emit("stroke_removed", {"id": stroke["id"]}, room=room, include_self=False)


@socketio.on("clear_canvas")
def handle_clear():
    room = current_room()
    if not room:
        return
    boards[room] = []
    emit("clear_board", room=room, include_self=False)


@socketio.on("disconnect")
def handle_disconnect(*args):
    room = members.pop(request.sid, None)
    if not room:
        return
    if any(r == room for r in members.values()):
        send_user_count(room)
    else:
        boards.pop(room, None)  # الغرفة فاضية، نظّف الذاكرة


if __name__ == "__main__":
    print("✨ Live Canvas: http://127.0.0.1:5000")
    socketio.run(app, host="127.0.0.1", port=5000, debug=True)