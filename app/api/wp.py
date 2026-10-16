from __future__ import annotations

import mimetypes
import os
import re
import uuid

from .http import ApiError, RestBase


POST_LIST_FIELDS = "id,title,status,date,categories,slug"


class WPClient(RestBase):
    def __init__(self, base_url: str, user: str, app_password: str, client=None):
        super().__init__(base_url, (user, (app_password or "").strip()), "/wp/v2", client)

    # ---- connection ----------------------------------------------------
    def me(self) -> dict:
        return self.json("GET", "/users/me", params={"context": "edit"})

    # ---- posts ---------------------------------------------------------
    def posts(self, page=1, per_page=20, search="", status="any", category=None, orderby="date", order="desc"):
        params = {
            "page": page, "per_page": per_page, "status": status, "orderby": orderby,
            "order": order, "context": "edit", "_fields": POST_LIST_FIELDS,
        }
        if search:
            params["search"] = search
        if category:
            params["categories"] = category
        return self.page("/posts", params)

    def post(self, post_id: int) -> dict:
        return self.json("GET", f"/posts/{post_id}", params={"context": "edit"})

    def save_post(self, post_id: int | None, data: dict) -> dict:
        if post_id:
            return self.json("POST", f"/posts/{post_id}", json=data)
        return self.json("POST", "/posts", json=data)

    def delete_post(self, post_id: int, force: bool = False) -> dict:
        return self.json("DELETE", f"/posts/{post_id}", params={"force": "true" if force else "false"})

    def count_posts(self, status: str) -> int:
        _d, total, _p = self.page("/posts", {"per_page": 1, "status": status, "context": "edit"})
        return total

    # ---- taxonomies ----------------------------------------------------
    def categories(self) -> list:
        return self.all_pages("/categories", {"hide_empty": "false"})

    def create_category(self, name: str, parent: int = 0) -> dict:
        return self.json("POST", "/categories", json={"name": name, "parent": parent})

    def tags(self) -> list:
        return self.all_pages("/tags")

    def create_tag(self, name: str) -> dict:
        try:
            return self.json("POST", "/tags", json={"name": name})
        except ApiError as e:
            # WP answers "term_exists" with the existing id
            if isinstance(e.payload, dict) and e.payload.get("code") == "term_exists":
                return {"id": e.payload.get("data", {}).get("term_id"), "name": name}
            raise

    def tags_by_ids(self, ids: list[int]) -> list:
        if not ids:
            return []
        out: list = []
        ids = list(ids)
        # WordPress caps per_page at 100; a post may reference more tags than that.
        for i in range(0, len(ids), 100):
            chunk = ids[i:i + 100]
            out.extend(self.json("GET", "/tags", params={"include": ",".join(str(x) for x in chunk), "per_page": 100}))
        return out

    # ---- media ---------------------------------------------------------
    def media(self, page=1, per_page=30, search="", media_type=""):
        params = {"page": page, "per_page": per_page, "context": "edit", "orderby": "date", "order": "desc"}
        if search:
            params["search"] = search
        if media_type:
            params["media_type"] = media_type
        return self.page("/media", params)

    def upload_media(self, path: str, alt_text: str = "") -> dict:
        name = os.path.basename(path)
        ext = os.path.splitext(name)[1].lower()
        if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
            name = f"{uuid.uuid4().hex[:10]}{ext}"
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        with open(path, "rb") as f:
            content = f.read()
        item = self.json(
            "POST", "/media", content=content,
            headers={"Content-Disposition": f'attachment; filename="{name}"', "Content-Type": ctype},
        )
        if alt_text:
            item = self.update_media(item["id"], {"alt_text": alt_text})
        return item

    def update_media(self, media_id: int, data: dict) -> dict:
        return self.json("POST", f"/media/{media_id}", json=data)

    def delete_media(self, media_id: int) -> dict:
        return self.json("DELETE", f"/media/{media_id}", params={"force": "true"})


def media_thumb(item: dict) -> str:
    sizes = (item.get("media_details") or {}).get("sizes") or {}
    for key in ("thumbnail", "medium"):
        if key in sizes and sizes[key].get("source_url"):
            return sizes[key]["source_url"]
    return item.get("source_url", "")
