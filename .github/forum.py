#!/usr/bin/env python3
# Copies the SnapOS discussions as plain text for the website. Nothing the
# writers send is kept as HTML: only text, numbers and checked names.
import json, os, re, urllib.request

OWNER, REPO = "snapos-distro", "forum"
LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
AVATAR = re.compile(r"^https://avatars\.githubusercontent\.com/[A-Za-z0-9/._?=&%-]{1,300}$")
STAMP = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

Q = """query($owner: String!, $repo: String!, $after: String) {
  repository(owner: $owner, name: $repo) {
    discussionCategories(first: 25) { nodes { name slug } }
    discussions(first: 50, after: $after, orderBy: {field: UPDATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title createdAt updatedAt bodyText upvoteCount isAnswered
        category { slug }
        author { login avatarUrl }
        comments(first: 60) {
          totalCount
          nodes {
            createdAt bodyText isAnswer
            author { login avatarUrl }
            replies(first: 60) { nodes { createdAt bodyText author { login avatarUrl } } }
          }
        }
      }
    }
  }
}"""

def ask(after=None):
    body = json.dumps({"query": Q, "variables": {"owner": OWNER, "repo": REPO, "after": after}}).encode()
    req = urllib.request.Request("https://api.github.com/graphql", body,
                                 {"Authorization": "bearer " + os.environ["GITHUB_TOKEN"], "User-Agent": "snapos-forum"})
    data = json.load(urllib.request.urlopen(req, timeout=60))
    if "errors" in data:
        raise SystemExit("GitHub said: " + json.dumps(data["errors"])[:500])
    return data["data"]["repository"]

def text(s, limit):
    s = "" if s is None else str(s)
    s = "".join(c for c in s if c in "\n\t" or ord(c) >= 32)   # no control characters
    return s[:limit]

def person(a):
    login = (a or {}).get("login") or ""
    avatar = (a or {}).get("avatarUrl") or ""
    if not LOGIN.match(login):
        return {"login": "ghost", "avatar": ""}
    return {"login": login, "avatar": avatar if AVATAR.match(avatar) else ""}

def when(s):
    return s if isinstance(s, str) and STAMP.match(s) else ""

def number(n):
    return n if isinstance(n, int) and 0 <= n < 10**9 else 0

repo = ask()
nodes, page = repo["discussions"]["nodes"], repo["discussions"]["pageInfo"]
while page["hasNextPage"] and len(nodes) < 300:
    more = ask(page["endCursor"])["discussions"]
    nodes += more["nodes"]
    page = more["pageInfo"]

slug = re.compile(r"^[a-z0-9-]{1,60}$")
categories = [{"name": text(c["name"], 60), "slug": c["slug"]} for c in repo["discussionCategories"]["nodes"] if slug.match(c["slug"] or "")]
topics = []
for t in nodes:
    comments = []
    for c in t["comments"]["nodes"]:
        comments.append({
            "author": person(c["author"]), "at": when(c["createdAt"]), "text": text(c["bodyText"], 20000),
            "answer": bool(c["isAnswer"]),
            "replies": [{"author": person(r["author"]), "at": when(r["createdAt"]), "text": text(r["bodyText"], 20000)}
                        for r in c["replies"]["nodes"]],
        })
    cat = (t["category"] or {}).get("slug") or ""
    topics.append({
        "number": number(t["number"]), "title": text(t["title"], 300), "category": cat if slug.match(cat) else "",
        "author": person(t["author"]), "created": when(t["createdAt"]), "updated": when(t["updatedAt"]),
        "text": text(t["bodyText"], 40000), "votes": number(t["upvoteCount"]), "answered": bool(t["isAnswered"]),
        "replies": number(t["comments"]["totalCount"]), "comments": comments,
    })

print(json.dumps({"categories": categories, "topics": topics}, ensure_ascii=False, separators=(",", ":")))
