"""Freeze the task prompt against saved local chess runs, not regenerated old code.

The first ten were captured from both fable_implicit_<id>/prompt.md and
opus_implicit_<id>/prompt.md in the saved tournament reference on 2026-09-15.
Both saved copies matched for every position. Only the checkout root and reset
tool spelling are normalized; no other whitespace/content changes are hidden.
The twenty positions added on 2026-09-16 have no saved run; their hashes are
build.py's render on the day they were added, frozen the same way.
This does not assert equivalence of the native CLI system context or tools.
On 2026-11-23 the prompt was changed (move cap stated, answer block no longer a
copyable win; docs/chess_go_prompt_fix.md) and every hash was re-frozen to it.
"""
import hashlib
import json
from pathlib import Path

import pytest

from tasks.chess.build import POSITIONS, game_block

ROOT = Path(__file__).resolve().parents[1]
CHESS_PROMPTS = {
    "LR4pA": "5dfb066a60bc657b398028f85597907588d3902461de3bf96753b96f61a2bfc0",
    "FBLBF": "0fbcc8f2f4c0ed53ca06f1e6a52f7252d53284ccc9137f67bf664ae4e4642be8",
    "2OINf": "0211a564b40ed1ccacb9b21ce85681425a973e909cc440d5daa281abfdfb1a08",
    "7xQxM": "7a0b3d64561c08aff1f369ab3561c3c0a807537e93b73a0da58fe1130fad61aa",
    "7LNs4": "f22c39f129cf32f165fb439ae7b61e6ce0921274075960ebcc455c97b7fb9123",
    "jtMlU": "41cc98de972bfafdfe27bcd4ae404ac7991f7129f5c765b93481c4b40ac2fe21",
    "PNMjr": "cc84729f3fec1e594fcd868203640c13f773b9496ceccfee575126198b0acd5f",
    "hzb8g": "04c3680976af3cd65a2d2eed61f3076220849e78caf57a4bfa6f4996f16f6d88",
    "O2NPN": "4199bd7bcb6d47a05634cb1e1788fe4d9d70edbbeac07858fe17475f58676fba",
    "E2lAF": "e3f397d2ded514b7b61c7d938e287094cd94eac03e1d22d203a759d28e1a8ec6",
    "r4ZT3": "3fc398323079a1253ae0126be1a875474eac69899fc11b5acdc8bce7e90c88fa",
    "bDHie": "328ce06d8081228f23c74d97c10bf03359abd5a96733a44e93203e34473ae85d",
    "wUxAX": "bd8786b46178de026312d26623dba211264eed4b222925aaa8c2e861a5b45ac0",
    "GD6OA": "582a2db5ac65d057a9d2defc3ff389e8d70ac718c376e35eef21d162de2ae4c4",
    "giVL1": "750e170a572b96dc014356b8cfcf2024ac1087b9ff9b0c154e5e0157d2fc9544",
    "HywU8": "05fc2fc46b47af1d75926d179683d4890a3165cd029afc4a1e4eefc66d047e78",
    "zCEI6": "219a4e10f78b93ad9a8d673391d7398407e897c7d538ab1f710fe319c99cd421",
    "rYUkb": "8e3de2037243131d48658d75c72532fa3fbd416236c2f2a550705c5f67a9dbb3",
    "O0aIK": "eb18c5692c949341863e0a7e4b8b553b33f54dcb5daa17f4821863a6862339ea",
    "z3Bcg": "553dd945b17f65b81a6b0df08858dd7ea663019e9954ab763b697f5008dee9b9",
    "Bx8w7": "dc43af42353851ecf7e6cd71fc84709859936bd8e54b7cf6eab22fe95b9c78f3",
    "nf2R3": "bf0cd70cdf78852b0e251cc6fc819227f6769cf97c738249e8ca51b0343027bf",
    "7rVRl": "bec0b0a9ddb575b6c8afa29ef5807a5f9c02a445da23904616dae29219bc76e0",
    "5G6a7": "aa86e14a854af546f7c4e2cee9a970feb173b615985ce7cf074b78bdc71a33dd",
    "KkvSM": "2bd141dd09e7ff3aa30f15ba3d3b672ac3d34fe0b19c978284c8dab34c439282",
    "IG9rB": "5aba944a5b2781cb74fe54368295fb4eba28840128bb8ded94d62045e2a50f3f",
    "VH7m9": "fea7c0ef3069287d18948a75ca1f49bb38d43edec25f7c13824423989aad82eb",
    "Xg4mc": "728bacff51c176602912fe452c49b25d629b055f7e6be51332e9194652454a47",
    "MwNQP": "a23d16459f8c5c334b1b182bb058a0434e024e2491fb97277da1b8d1668af8cd",
    "f2EIS": "82e8c9d667109230044b2566daeb773ef68654c912403f6abede80375e10b10e",
}


@pytest.mark.parametrize("template_name", ["instruction.md", "instruction_chess.md"])
@pytest.mark.parametrize("position", POSITIONS)
def test_task_prompt_matches_saved_chess(position, template_name):
    fixture = json.loads((ROOT / f"tasks/chess/fixtures/tournament_{position}.json").read_text())
    template = (ROOT / "tasks/chess/prompts" / template_name).read_text()
    prompt = template.replace("{{input}}", game_block(fixture)).strip()
    prompt = prompt.replace("`/workspace`", "`/episode/chess-evals`")
    prompt = prompt.replace("`play_move` with `reset`", "`reset_game`")
    assert hashlib.sha256(prompt.encode()).hexdigest() == CHESS_PROMPTS[position]


def test_baseline_covers_every_current_position():
    assert set(POSITIONS) == set(CHESS_PROMPTS)
