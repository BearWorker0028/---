# -*- coding: utf-8 -*-
import re

with open(r'local_web\app.py', 'r', encoding='utf-8') as f:
    content = f.read()

target = """@app.route('/api/temperature_stream')
def temperature_stream():

            encoded = json.dumps(payload, ensure_ascii=False)

            if encoded != last_payload:

                yield f"event: temperatures\\ndata: {encoded}\\n\\n"

                last_payload = encoded

            else:

                yield ": keepalive\\n\\n"

            time.sleep(1)

    return Response(event_stream(), mimetype='text/event-stream')"""

replacement = """@app.route('/api/temperature_stream')
def temperature_stream():
    @stream_with_context
    def event_stream():
        last_payload = None
        while True:
            payload = _latest_temperatures_payload()
            encoded = json.dumps(payload, ensure_ascii=False)
            if encoded != last_payload:
                yield f"event: temperatures\\ndata: {encoded}\\n\\n"
                last_payload = encoded
            else:
                yield ": keepalive\\n\\n"
            time.sleep(1)

    return Response(event_stream(), mimetype='text/event-stream')"""

# Normalize line endings for replacement
content_norm = content.replace('\r\n', '\n')
target_norm = target.replace('\r\n', '\n')
replacement_norm = replacement.replace('\r\n', '\n')

if target_norm in content_norm:
    new_content = content_norm.replace(target_norm, replacement_norm)
    with open(r'local_web\app.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("SUCCESS: Cleaned app.py")
else:
    print("TARGET NOT FOUND IN APP.PY")
