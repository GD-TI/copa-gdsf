import base64
import json
import os
import time
from datetime import date
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS

load_dotenv()

app = Flask(__name__)
CORS(app)

LOGIN_URL = "https://server.newcorban.com.br/api/v2/login"
RANKING_URL = "https://server.newcorban.com.br/system/ranking.php"

# Vendor IDs excluded from the Copa GD competition
NOT_VENDEDOR = [
    "5450", "1111", "1275", "1276", "1277", "1799", "1929", "1930",
    "2202", "21602", "1437", "10028", "14980", "1013", "18676", "24693",
    "2791", "10026", "10027", "13315", "602", "1021", "1022", "1039",
    "1040", "1041", "1053", "1055", "1100", "12181", "14979", "14981",
    "15468", "15609", "16208",
]

_token: str | None = None
_token_ts: float = 0.0
TOKEN_TTL = 3000  # 50 min — tokens expire at 1h, refresh before that


def _login() -> str:
    resp = requests.post(
        LOGIN_URL,
        data={
            "empresa": os.getenv("EMPRESA", "grupodigital"),
            "ip": os.getenv("IP", "189.79.55.135"),
            "usuario": os.getenv("USUARIO"),
            "senha": os.getenv("SENHA"),
            "p": "ranking",
        },
        timeout=15,
    )
    resp.raise_for_status()
    body = resp.json()
    token = (
        body.get("token")
        or body.get("access_token")
        or (body.get("data") or {}).get("token")
    )
    if not token:
        raise ValueError(f"Token not found in login response: {list(body.keys())}")
    return token


def get_token() -> str:
    global _token, _token_ts
    if _token and (time.time() - _token_ts) < TOKEN_TTL:
        return _token
    _token = _login()
    _token_ts = time.time()
    return _token


def build_i_param(start_date: str, end_date: str) -> str:
    intervalo = "today" if start_date == end_date else "personalizado"
    params = {
        "first_level": "vendedores",
        "second_level": "vendedores",
        "type": "agrupado",
        "metrica": "qtd_propostas",
        "banco": [], "not_banco": [],
        "promotora": [], "not_promotora": [],
        "status": [], "not_status": [],
        "produto": [], "not_produto": [],
        "convenio": [], "not_convenio": [],
        "equipe": [], "not_equipe": [],
        "vendedor": [],
        "not_vendedor": NOT_VENDEDOR,
        "vendedor_participante": [], "not_vendedor_participante": [],
        "tabela": [], "not_tabela": [],
        "origem": [], "not_origem": [],
        "franquia": [], "not_franquia": [],
        "ver_como_franquia": False,
        "comissionado": False,
        "nao_comissionado": False,
        "estornado": False,
        "nao_estornado": False,
        "onlyDuplicadas": False,
        "hideDuplicadas": False,
        "hide_repassado": False,
        "data": {
            "tipo": "cadastro",
            "startDate": start_date,
            "endDate": end_date,
            "intervalo": intervalo,
        },
    }
    json_str = json.dumps(params, separators=(",", ":"), ensure_ascii=False)
    return base64.b64encode(quote(json_str).encode()).decode()


@app.route("/api/sellers")
def api_sellers():
    today = date.today().isoformat()
    start = request.args.get("start", today)
    end = request.args.get("end", today)

    try:
        token = get_token()
        i_param = build_i_param(start, end)

        resp = requests.get(
            RANKING_URL,
            params={"action": "performance", "i": i_param},
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()

        result = data.get("result") or {}
        seen: dict[str, dict] = {}

        for _group_name, group in result.items():
            second = group.get("second_level") or {}
            for _sname, sinfo in second.items():
                sid = str(sinfo.get("filter_value", "")).strip()
                if not sid:
                    continue
                val = float(sinfo.get("valor_referencia") or 0)
                existing = seen.get(sid)
                if existing is None or val > float(existing.get("valor_referencia") or 0):
                    seen[sid] = sinfo

        sellers = [
            {
                "id": str(s.get("filter_value", "")),
                "name": s.get("name", ""),
                "value": float(s.get("valor_referencia") or 0),
                "metaInd": float(s.get("valor_meta") or 0),
                "image": s.get("image", ""),
                "qtd_propostas": int(s.get("qtd_propostas") or 0),
            }
            for s in seen.values()
        ]
        sellers.sort(key=lambda x: x["value"], reverse=True)

        return jsonify({"ok": True, "sellers": sellers})

    except Exception as exc:
        global _token
        _token = None  # force re-auth on next call
        return jsonify({"ok": False, "error": str(exc)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=bool(os.getenv("DEBUG", "")))
