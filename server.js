import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';

dotenv.config();

const app = express();
app.use(cors());

const LOGIN_URL  = 'https://server.newcorban.com.br/api/v2/login';
const RANKING_URL = 'https://server.newcorban.com.br/system/ranking.php';

const NOT_VENDEDOR = [
  '5450','1111','1275','1276','1277','1799','1929','1930',
  '2202','21602','1437','10028','14980','1013','18676','24693',
  '2791','10026','10027','13315','602','1021','1022','1039',
  '1040','1041','1053','1055','1100','12181','14979','14981',
  '15468','15609','16208',
];

let _token   = null;
let _tokenTs = 0;
const TOKEN_TTL = 50 * 60 * 1000; // 50 min em ms (token expira em 1h)

async function login() {
  const body = new URLSearchParams({
    empresa: process.env.EMPRESA ?? 'grupodigital',
    ip:      process.env.IP      ?? '189.79.55.135',
    usuario: process.env.USUARIO,
    senha:   process.env.SENHA,
    p:       'ranking',
  });

  const res = await fetch(LOGIN_URL, { method: 'POST', body });
  if (!res.ok) throw new Error(`Login falhou: HTTP ${res.status}`);

  const data = await res.json();
  const token = data.token ?? data.access_token ?? data?.data?.token;
  if (!token) throw new Error(`Token não encontrado na resposta: ${JSON.stringify(Object.keys(data))}`);
  return token;
}

async function getToken() {
  if (_token && Date.now() - _tokenTs < TOKEN_TTL) return _token;
  _token   = await login();
  _tokenTs = Date.now();
  return _token;
}

function buildIParam(startDate, endDate) {
  const intervalo = startDate === endDate ? 'today' : 'personalizado';
  const params = {
    first_level: 'vendedores', second_level: 'vendedores',
    type: 'agrupado', metrica: 'qtd_propostas',
    banco: [], not_banco: [],
    promotora: [], not_promotora: [],
    status: [], not_status: [],
    produto: [], not_produto: [],
    convenio: [], not_convenio: [],
    equipe: [], not_equipe: [],
    vendedor: [], not_vendedor: NOT_VENDEDOR,
    vendedor_participante: [], not_vendedor_participante: [],
    tabela: [], not_tabela: [],
    origem: [], not_origem: [],
    franquia: [], not_franquia: [],
    ver_como_franquia: false, comissionado: false, nao_comissionado: false,
    estornado: false, nao_estornado: false,
    onlyDuplicadas: false, hideDuplicadas: false, hide_repassado: false,
    data: { tipo: 'cadastro', startDate, endDate, intervalo },
  };
  // Same encoding the original browser uses: btoa(encodeURIComponent(JSON.stringify(...)))
  return Buffer.from(encodeURIComponent(JSON.stringify(params))).toString('base64');
}

app.get('/api/sellers', async (req, res) => {
  const today = new Date().toISOString().slice(0, 10);
  const start = req.query.start ?? today;
  const end   = req.query.end   ?? today;

  try {
    const token = await getToken();

    const url = new URL(RANKING_URL);
    url.searchParams.set('action', 'performance');
    url.searchParams.set('i', buildIParam(start, end));

    const apiRes = await fetch(url.toString(), {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!apiRes.ok) throw new Error(`Ranking API: HTTP ${apiRes.status}`);

    const data   = await apiRes.json();
    const result = data.result ?? {};
    const seen   = new Map();

    for (const group of Object.values(result)) {
      for (const sinfo of Object.values(group.second_level ?? {})) {
        const sid = String(sinfo.filter_value ?? '').trim();
        if (!sid) continue;
        const val = parseFloat(sinfo.valor_referencia ?? 0);
        if (!seen.has(sid) || val > parseFloat(seen.get(sid).valor_referencia ?? 0)) {
          seen.set(sid, sinfo);
        }
      }
    }

    const sellers = Array.from(seen.values())
      .map(s => ({
        id:            String(s.filter_value ?? ''),
        name:          s.name ?? '',
        value:         parseFloat(s.valor_referencia ?? 0),
        metaInd:       parseFloat(s.valor_meta ?? 0),
        image:         s.image ?? '',
        qtd_propostas: parseInt(s.qtd_propostas ?? 0, 10),
      }))
      .sort((a, b) => b.value - a.value);

    res.json({ ok: true, sellers });

  } catch (err) {
    _token = null; // força novo login na próxima chamada
    console.error('[sellers]', err.message);
    res.status(500).json({ ok: false, error: err.message });
  }
});

const PORT = process.env.PORT ?? 5000;
app.listen(PORT, '0.0.0.0', () =>
  console.log(`Copa GD backend rodando em :${PORT}`)
);
