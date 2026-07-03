import socket
import sys
import webbrowser

import uvicorn

PORT = 8000

def port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

if __name__ == '__main__':
    if port_in_use(PORT):
        print(f"[PDFabric] ERROR: Port {PORT} is already in use.")
        print("Close the other application or change the port.")
        input("Press Enter to exit...")
        sys.exit(1)

    print(f"[PDFabric] Starting server at http://localhost:{PORT}")
    webbrowser.open(f"http://localhost:{PORT}")
    uvicorn.run("app.main:app", host="127.0.0.1", port=PORT)
