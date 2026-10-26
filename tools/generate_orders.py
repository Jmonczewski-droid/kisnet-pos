#!/usr/bin/env python3
"""
Set up tickets for a person to work on the screens.

The tool creates parties with random names and sends their orders through the same API the screens use.
Nothing after that is done for you: bumping, editing, voiding and closing are left to the person using the screens.

It logs in as the staff only to create the tickets, then logs them all out again at the end, so the
screens are free for you to log in.

Usage:
    venv/bin/python tools/generate_orders.py --url http://127.0.0.1:8001 --count 10
"""
import argparse
import random
import sys

import httpx

PIN = "1234"
STAFF = ("HOST1", "SRV1", "SRV2", "SRV3", "SRV4", "KIT1", "BAR1")
SERVER_IDS = {"SRV1": 2, "SRV2": 6, "SRV3": 7, "SRV4": 8}
FIRST_NAMES = ["Ava", "Liam", "Mia", "Noah", "Zoe", "Eli", "Nora", "Owen", "Ivy", "Jack", "Lena", "Mateo",
               "Priya", "Omar", "Sofia", "Kai", "Hana", "Diego", "Maya", "Theo", "Ruby", "Samir", "Chloe", "Felix"]
LAST_NAMES = ["Garcia", "Nguyen", "Patel", "Okafor", "Kowalski", "Haddad", "Brooks", "Silva", "Tanaka", "Murphy",
              "Lindqvist", "Moreau", "Rossi", "Adeyemi", "Chen", "Schmidt", "Rivera", "Kaur", "Ibrahim", "Dubois"]


class Api:
    def __init__(self, url: str):
        self.http = httpx.Client(base_url=url, timeout=30)
        self.tokens = {}

    def login_all(self):
        for code in STAFF:
            self.http.post("/api/v1/auth/clock-in", json={"code": code, "pin": PIN})  # 409: already on the clock
            response = self.http.post("/api/v1/auth/login", json={"code": code, "pin": PIN})
            if response.status_code != 200:
                raise SystemExit(f"Could not log in {code}: {response.status_code} {response.text}")
            self.tokens[code] = response.json()["token"]

    def logout_all(self):
        for code, token in self.tokens.items():
            self.http.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})

    def call(self, code: str, method: str, path: str, **kwargs):
        response = self.http.request(method, path, headers={"Authorization": f"Bearer {self.tokens[code]}"}, **kwargs)
        if response.status_code >= 400:
            raise RuntimeError(f"{code} {method} {path} -> {response.status_code}: {response.text[:200]}")
        return response.json()

    def free_seats(self, bar: bool) -> list:
        rows = self.call("HOST1", "GET", "/api/v1/seats")
        return [row["seat"] for row in rows
                if row["party"] is None and row["seat"].startswith("BAR") == bar]


def make_ticket(api: Api, rng: random.Random, at_bar: bool, second_round: bool) -> str:
    seats = api.free_seats(bar=at_bar)
    if not seats:
        raise RuntimeError("no free seat left for this kind of ticket")
    seat = rng.choice(seats)
    menu = api.call("HOST1", "GET", "/api/v1/menu")
    drinks = [m for m in menu if m["category"] == "bar"]
    food = [m for m in menu if m["category"] != "bar"]

    if at_bar:
        name = rng.choice(FIRST_NAMES)
        party = api.call("BAR1", "POST", "/api/v1/parties", json={"seat": seat, "party_name": name})
        server, lines = "BAR1", rng.sample(drinks, k=rng.randint(1, 3))
    else:
        server = rng.choice(list(SERVER_IDS))
        name = f"{rng.choice(LAST_NAMES)} party"
        party = api.call("HOST1", "POST", "/api/v1/parties", json={
            "seat": seat, "party_name": name, "party_size": rng.randint(1, 6), "server_id": SERVER_IDS[server]})
        lines = rng.sample(food, k=rng.randint(1, 3)) + rng.sample(drinks, k=rng.randint(0, 2))

    send = {"items": [{"menu_item_id": m["id"], "qty": rng.randint(1, 2), "notes": None} for m in lines],
            "updates": [], "voids": []}
    api.call(server, "POST", f"/api/v1/parties/{party['id']}/send", json=send)
    if second_round:
        extra = rng.choice(food if not at_bar else drinks)
        api.call(server, "POST", f"/api/v1/parties/{party['id']}/send", json={
            "items": [{"menu_item_id": extra["id"], "qty": 1, "notes": None}], "updates": [], "voids": []})
    return f"{seat:5} {name}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://127.0.0.1:8001", help="server to create the tickets on")
    parser.add_argument("--count", type=int, default=10, help="how many tickets to set up")
    parser.add_argument("--bar-share", type=float, default=0.4, help="share of tickets at bar seats (0-1)")
    parser.add_argument("--second-round", type=float, default=0.25,
                        help="share of tickets that get a second round of items (0-1)")
    parser.add_argument("--seed", type=int, default=None, help="random seed (default: different each run)")
    args = parser.parse_args(argv)

    rng = random.Random(args.seed)
    api = Api(args.url)
    api.login_all()
    try:
        made, failed = [], []
        for number in range(1, args.count + 1):
            try:
                made.append(make_ticket(api, rng, rng.random() < args.bar_share, rng.random() < args.second_round))
            except RuntimeError as error:
                failed.append(str(error))
                break
        print("Tickets ready for you (seat and party name):")
        for line in made:
            print(f"  {line}")
        print(f"Created {len(made)}" + (f", stopped early: {failed[0]}" if failed else "") + ".")
        return 0 if not failed else 1
    finally:
        api.logout_all()
        print("Staff logged out. Log in on the screens as anyone you like.")


if __name__ == "__main__":
    sys.exit(main())
