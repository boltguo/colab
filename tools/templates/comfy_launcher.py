"""Start pinned ComfyUI with narrow workflow aliases and Cloudflare compatibility."""
import os
import runpy
import sys
from pathlib import Path
from aiohttp import web


def add_workflow_aliases(manager, routes):
    originals = [route for route in routes
                 if getattr(route, "path", None) == "/userdata/{file}"
                 and getattr(route, "method", None) in {"GET", "POST", "DELETE"}]
    if {route.method for route in originals} != {"GET", "POST", "DELETE"}:
        raise RuntimeError("ComfyUI 工作流访问接口已变化，未安装兼容路由。")
    for route in originals:
        async def workflow_alias(request, handler=route.handler):
            file = request.match_info.get("file", "")
            user_root = manager.get_request_user_filepath(request, None, create_dir=False)
            candidate = manager.get_request_user_filepath(request, file, create_dir=False)
            if not user_root or not candidate:
                return web.Response(status=403)
            workflow_directory = os.path.join(user_root, "workflows")
            if os.path.islink(workflow_directory):
                return web.Response(status=403)
            workflow_root = os.path.realpath(workflow_directory)
            try:
                within = os.path.commonpath((workflow_root, os.path.realpath(candidate))) == workflow_root
            except ValueError:
                within = False
            if not within or os.path.realpath(candidate) == workflow_root:
                return web.Response(status=403)
            return await handler(request)
        routes.route(route.method, "/userdata/{file:workflows/[^/]+}")(workflow_alias)


def install_cf_middleware():
    import middleware.cache_middleware as cm
    orig_cache_control = cm.cache_control

    @web.middleware
    async def cf_safe_middleware(request, handler):
        response = await orig_cache_control(request, handler)
        if request.method == "GET" and request.path == "/" and getattr(response, "status", None) == 200:
            import server
            inst = getattr(server.PromptServer, "instance", None)
            web_root = getattr(inst, "web_root", None) if inst else None
            index_file = Path(web_root) / "index.html" if web_root else None
            if index_file and index_file.is_file():
                html = index_file.read_text(encoding="utf-8", errors="replace")
                html = html.replace("<script ", '<script data-cfasync="false" ')
                new_resp = web.Response(text=html, content_type="text/html")
                for k, v in response.headers.items():
                    if k.lower() not in {"content-length", "content-type", "etag", "last-modified"}:
                        new_resp.headers[k] = v
                new_resp.headers["Cache-Control"] = "no-store, no-transform, must-revalidate"
                response = new_resp
        if isinstance(response, web.StreamResponse) and not isinstance(response, web.WebSocketResponse) and not response.prepared:
            if getattr(response, "status", None) == 200 and (
                request.path.startswith("/assets/")
                or request.path.endswith((".woff2", ".woff", ".ttf"))
            ):
                response.headers["Cache-Control"] = "public, max-age=604800, immutable, no-transform"
            else:
                cc = response.headers.get("Cache-Control", "")
                if "no-transform" not in cc:
                    response.headers["Cache-Control"] = f"{cc}, no-transform" if cc else "no-transform"
            origin = request.headers.get("Origin")
            if origin and response.headers.get("Access-Control-Allow-Origin") == "*":
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Vary"] = "Origin"
        return response

    cm.cache_control = cf_safe_middleware


def main():
    comfy_root = Path("/content/ComfyUI")
    if comfy_root.is_symlink() or not (comfy_root / "main.py").is_file() or not (comfy_root / "comfy/options.py").is_file():
        raise RuntimeError("ComfyUI 源码目录缺失或无效。")
    os.chdir(comfy_root)
    sys.path.insert(0, str(comfy_root))
    sys.argv[0] = str(comfy_root / "main.py")
    import comfy.options
    comfy.options.enable_args_parsing()
    install_cf_middleware()
    from app.user_manager import UserManager
    original = UserManager.add_routes

    def compatible_routes(self, routes):
        original(self, routes)
        add_workflow_aliases(self, routes)

    UserManager.add_routes = compatible_routes
    runpy.run_path("main.py", run_name="__main__")


if __name__ == "__main__":
    main()
