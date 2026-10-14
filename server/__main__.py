"""python -m server로 시작합니다."""

import argparse
import logging
import threading
import webbrowser

from werkzeug.serving import make_server

from server.app import create_app


def main():
    parser = argparse.ArgumentParser(description="IBCM 업무 앱을 시작합니다.")
    parser.add_argument("--host", default="127.0.0.1", help="서버 주소")
    parser.add_argument("--port", type=int, default=8000, help="서버 포트")
    parser.add_argument("--no-browser", action="store_true", help="브라우저 자동 열기 생략")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    app = create_app()
    server = make_server(args.host, args.port, app, threaded=True)
    url = f"http://{args.host}:{args.port}"
    print(f"IBCM 실행 중: {url}", flush=True)
    if not args.no_browser:
        opener = threading.Timer(0.4, webbrowser.open, args=(url,))
        opener.daemon = True
        opener.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nIBCM을 종료했습니다.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
