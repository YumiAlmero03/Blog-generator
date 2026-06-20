from flask import Response, jsonify, stream_with_context

from app.events.generation_events import cancel_generation, get_generation_status, stream_generation_events


def generation_status(token: str):
    return jsonify(get_generation_status(token))


def cancel_generation_status(token: str):
    cancel_generation(token)
    return jsonify({"cancelled": True})


def generation_events(token: str):
    return Response(
        stream_with_context(stream_generation_events(token)),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
