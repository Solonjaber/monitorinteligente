"""
anglis_alertas_api.py
API REST - Sistema de Alertas Anglis
v1.3 - 2026-06-18

Endpoints:
  GET  /health
  GET  /api/alertas/campos               -> lista mapeamento de campos
  POST /api/alertas/campos               -> salva array completo (upsert)
  GET  /api/alertas/regras               -> lista regras
  POST /api/alertas/regras               -> salva array completo (upsert)
  GET  /api/alertas/logs                 -> lista logs com filtros
  POST /api/alertas/logs                 -> insere log (usado pelo engine)
  PATCH /api/alertas/logs/{id}/lido      -> marca/desmarca lido (registra usuario)
  DELETE /api/alertas/logs               -> apaga logs por filtro
  POST /api/alertas/logs/{id}/acoes      -> registra acao do operador sobre o alerta
  GET  /api/alertas/logs/{id}/acoes      -> lista acoes de um alerta
  GET  /api/alertas/telefones            -> lista telefones (filtro por franquia_cod_id)
  POST /api/alertas/telefones            -> cria telefone
  PUT  /api/alertas/telefones/{id}       -> atualiza telefone
  DELETE /api/alertas/telefones/{id}     -> remove telefone
  GET  /api/presence/residentes          -> pares distintos (residente, comodo) de presence_summary
  GET  /api/presence/eventos             -> eventos de um residente+comodo especifico
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Any
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# ---------------------------------------------------------------------------
# Configuracao
# ---------------------------------------------------------------------------

DB_CONFIG = {
    "database": "anglismonitoramento",
    "user":     "anglisdbadm",
    "password": "anglis777power144",
    "host":     "reports.anglis.com.br",
    "port":     5432,
}

API_PORT = int(os.getenv("ALERTAS_API_PORT", "8088"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("anglis_alertas_api")

# ---------------------------------------------------------------------------
# App FastAPI
# ---------------------------------------------------------------------------

app = FastAPI(title="Anglis Alertas API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Conexao com o banco
# ---------------------------------------------------------------------------

@contextmanager
def get_conn():
    conn = psycopg2.connect(connect_timeout=10, **DB_CONFIG)
    conn.autocommit = False
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# Modelos Pydantic
# ---------------------------------------------------------------------------

class CampoItem(BaseModel):
    value: str
    label: str
    type: str = "number"
    placeholder: Optional[str] = None

class RegraCondicao(BaseModel):
    campo: str
    operador: str
    valor: Any

class RegraItem(BaseModel):
    id: str
    nome: str
    descricao: Optional[str] = None
    ativa: bool = True
    tipo_alerta: Optional[str] = None
    criticidade: Optional[str] = None
    silence_duration: int = 300
    canais: List[str] = []
    condicoes: List[Any] = []
    logicalOperator: str = "AND"
    escopo_franquia: Optional[str] = None
    escopo_residente: Optional[str] = None
    escopo_comodo: Optional[str] = None
    escopo_device: Optional[Any] = None
    template_mensagem: Optional[str] = None

class LogItem(BaseModel):
    regra_id: Optional[str] = None
    regra_nome: str
    criticidade: Optional[str] = None
    franquia_nome: Optional[str] = None
    franquia_cod_id: Optional[str] = None
    residente_nome: Optional[str] = None
    residente_cod_id: Optional[str] = None
    comodo_nome: Optional[str] = None
    comodo_local: Optional[str] = None
    device_id: Optional[str] = None
    canais: Optional[List[str]] = []
    condicoes_match: Optional[Any] = None

class MarcarLidoItem(BaseModel):
    lido: bool = True
    lido_por: Optional[str] = None

class AcaoItem(BaseModel):
    tipo: str
    descricao: str
    usuario: Optional[str] = None

class TelefoneItem(BaseModel):
    franquia_cod_id: str
    franquia_nome: Optional[str] = None
    nome_contato: Optional[str] = None
    telefone: str
    canal: str = "sms"
    ativo: bool = True
    regra_id: Optional[str] = None

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

# ---------------------------------------------------------------------------
# Campos
# ---------------------------------------------------------------------------

@app.get("/api/alertas/campos")
def listar_campos():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT value, label, type, placeholder FROM mapeamento_de_campos ORDER BY id")
            rows = cur.fetchall()
    return [dict(r) for r in rows]


@app.post("/api/alertas/campos")
def salvar_campos(campos: List[CampoItem]):
    """Substitui todos os campos pelo array enviado (upsert por value)."""
    if not campos:
        raise HTTPException(status_code=400, detail="Lista de campos vazia.")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM mapeamento_de_campos")
            for c in campos:
                cur.execute(
                    """
                    INSERT INTO mapeamento_de_campos (value, label, type, placeholder)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (c.value, c.label, c.type, c.placeholder),
                )
    return {"success": True, "message": f"{len(campos)} campos salvos."}

# ---------------------------------------------------------------------------
# Regras
# ---------------------------------------------------------------------------

def _row_to_regra(r: dict) -> dict:
    """Converte row do banco para o formato esperado pelo frontend."""
    condicoes = r.get("condicoes") or []
    if isinstance(condicoes, str):
        condicoes = json.loads(condicoes)

    canais = r.get("canais") or []

    escopo_device = r.get("escopo_device")
    if escopo_device is not None:
        try:
            escopo_device = int(escopo_device)
        except (ValueError, TypeError):
            pass

    return {
        "id": r["id"],
        "nome": r["nome"],
        "descricao": r.get("descricao"),
        "ativa": r.get("ativa", True),
        "tipo_alerta": r.get("tipo_alerta"),
        "criticidade": r.get("criticidade"),
        "silence_duration": r.get("silence_duration", 300),
        "canais": canais,
        "condicoes": condicoes,
        "logicalOperator": r.get("logical_operator", "AND"),
        "escopo_franquia": r.get("escopo_franquia"),
        "escopo_residente": r.get("escopo_residente"),
        "escopo_comodo": r.get("escopo_comodo"),
        "escopo_device": escopo_device,
        "template_mensagem": r.get("template_mensagem"),
    }


@app.get("/api/alertas/regras")
def listar_regras():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM regras ORDER BY created_at")
            rows = cur.fetchall()
    return [_row_to_regra(dict(r)) for r in rows]


@app.post("/api/alertas/regras")
def salvar_regras(regras: List[RegraItem]):
    """Upsert: insere novas, atualiza existentes, remove as que nao vieram."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            ids_novos = [r.id for r in regras]

            # Remove regras que nao estao na lista enviada
            if ids_novos:
                cur.execute(
                    "DELETE FROM regras WHERE id != ALL(%s)",
                    (ids_novos,),
                )
            else:
                cur.execute("DELETE FROM regras")

            for r in regras:
                cur.execute(
                    """
                    INSERT INTO regras (
                        id, nome, descricao, ativa, tipo_alerta, criticidade,
                        silence_duration, canais, condicoes, logical_operator,
                        escopo_franquia, escopo_residente, escopo_comodo, escopo_device,
                        template_mensagem, created_at, updated_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, NOW(), NOW())
                    ON CONFLICT (id) DO UPDATE SET
                        nome              = EXCLUDED.nome,
                        descricao         = EXCLUDED.descricao,
                        ativa             = EXCLUDED.ativa,
                        tipo_alerta       = EXCLUDED.tipo_alerta,
                        criticidade       = EXCLUDED.criticidade,
                        silence_duration  = EXCLUDED.silence_duration,
                        canais            = EXCLUDED.canais,
                        condicoes         = EXCLUDED.condicoes,
                        logical_operator  = EXCLUDED.logical_operator,
                        escopo_franquia   = EXCLUDED.escopo_franquia,
                        escopo_residente  = EXCLUDED.escopo_residente,
                        escopo_comodo     = EXCLUDED.escopo_comodo,
                        escopo_device     = EXCLUDED.escopo_device,
                        template_mensagem = EXCLUDED.template_mensagem,
                        updated_at        = NOW()
                    """,
                    (
                        r.id, r.nome, r.descricao, r.ativa, r.tipo_alerta, r.criticidade,
                        r.silence_duration,
                        r.canais,
                        json.dumps(r.condicoes),
                        r.logicalOperator,
                        r.escopo_franquia, r.escopo_residente, r.escopo_comodo,
                        str(r.escopo_device) if r.escopo_device is not None else None,
                        r.template_mensagem,
                    ),
                )
    return {"success": True, "message": f"{len(regras)} regras salvas."}

# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

@app.get("/api/alertas/logs")
def listar_logs(
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    franquia_cod_id: List[str] = Query(default=[]),
    regra_id: Optional[str] = None,
    desde: Optional[str] = None,
    ate: Optional[str] = None,
):
    filters = []
    params: list = []

    if franquia_cod_id:
        placeholders = ",".join(["%s"] * len(franquia_cod_id))
        filters.append(f"franquia_cod_id IN ({placeholders})")
        params.extend(franquia_cod_id)
    if regra_id:
        filters.append("regra_id = %s")
        params.append(regra_id)
    if desde:
        filters.append("disparado_em >= %s")
        params.append(desde)
    if ate:
        filters.append("disparado_em <= %s")
        params.append(ate)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    params += [limit, offset]

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT id, regra_id, regra_nome, criticidade,
                       franquia_nome, franquia_cod_id,
                       residente_nome, residente_cod_id,
                       comodo_nome, comodo_local, device_id, canais, condicoes_match,
                       disparado_em, lido, lido_por, lido_em
                FROM logs_alertas
                {where}
                ORDER BY disparado_em DESC
                LIMIT %s OFFSET %s
                """,
                params,
            )
            rows = cur.fetchall()

            cur.execute(f"SELECT COUNT(*) FROM logs_alertas {where}", params[:-2])
            total = cur.fetchone()["count"]

    result = []
    for r in rows:
        row = dict(r)
        if row.get("disparado_em"):
            row["disparado_em"] = row["disparado_em"].isoformat()
        if row.get("lido_em"):
            row["lido_em"] = row["lido_em"].isoformat()
        result.append(row)

    return {"total": total, "items": result}


@app.delete("/api/alertas/logs")
def apagar_logs(
    regra_id: Optional[str] = None,
    regra_nome: Optional[str] = None,
    franquia_cod_id: Optional[str] = None,
    ate: Optional[str] = None,
):
    """Apaga logs com base nos filtros fornecidos. Ao menos um filtro e obrigatorio."""
    if not any([regra_id, regra_nome, franquia_cod_id, ate]):
        raise HTTPException(status_code=400, detail="Informe ao menos um filtro: regra_id, regra_nome, franquia_cod_id ou ate.")

    filters = []
    params: list = []

    if regra_id:
        filters.append("regra_id = %s")
        params.append(regra_id)
    if regra_nome:
        filters.append("regra_nome ILIKE %s")
        params.append(f"%{regra_nome}%")
    if franquia_cod_id:
        filters.append("franquia_cod_id = %s")
        params.append(franquia_cod_id)
    if ate:
        filters.append("disparado_em <= %s")
        params.append(ate)

    where = "WHERE " + " AND ".join(filters)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM logs_alertas {where}", params)
            deleted = cur.rowcount

    return {"success": True, "deletados": deleted}


@app.patch("/api/alertas/logs/{log_id}/lido")
def marcar_lido(log_id: int, body: MarcarLidoItem):
    """Marca ou desmarca um log como lido, registrando quem e quando."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            if body.lido:
                cur.execute(
                    """
                    UPDATE logs_alertas
                    SET lido = true, lido_por = %s, lido_em = NOW()
                    WHERE id = %s
                    """,
                    (body.lido_por, log_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE logs_alertas
                    SET lido = false, lido_por = NULL, lido_em = NULL
                    WHERE id = %s
                    """,
                    (log_id,),
                )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Log nao encontrado.")
    return {"success": True, "lido": body.lido}


@app.post("/api/alertas/logs/{log_id}/acoes", status_code=201)
def registrar_acao(log_id: int, body: AcaoItem):
    """Registra uma acao do operador (atendimento, resolucao ou ignorar) sobre um alerta."""
    if body.tipo not in ("atendimento", "resolucao", "ignorar"):
        raise HTTPException(status_code=400, detail="tipo deve ser: atendimento, resolucao ou ignorar.")
    if not body.descricao or len(body.descricao.strip()) < 10:
        raise HTTPException(status_code=400, detail="descricao deve ter pelo menos 10 caracteres.")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM logs_alertas WHERE id = %s", (log_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Log nao encontrado.")
            cur.execute(
                """
                INSERT INTO acoes_alertas (log_id, tipo, descricao, usuario)
                VALUES (%s, %s, %s, %s)
                RETURNING id, registrado_em
                """,
                (log_id, body.tipo, body.descricao.strip(), body.usuario),
            )
            row = cur.fetchone()
    return {"success": True, "id": row[0], "registrado_em": row[1].isoformat()}


@app.get("/api/alertas/logs/{log_id}/acoes")
def listar_acoes(log_id: int):
    """Lista todas as acoes registradas para um alerta."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id FROM logs_alertas WHERE id = %s", (log_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Log nao encontrado.")
            cur.execute(
                """
                SELECT id, log_id, tipo, descricao, usuario, registrado_em
                FROM acoes_alertas
                WHERE log_id = %s
                ORDER BY registrado_em ASC
                """,
                (log_id,),
            )
            rows = cur.fetchall()
    result = []
    for r in rows:
        row = dict(r)
        if row.get("registrado_em"):
            row["registrado_em"] = row["registrado_em"].isoformat()
        result.append(row)
    return {"total": len(result), "items": result}


@app.post("/api/alertas/logs")
def inserir_log(log_item: LogItem):
    """Chamado pelo engine ao disparar um alerta."""
    condicoes_json = json.dumps(log_item.condicoes_match) if log_item.condicoes_match else None
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO logs_alertas (
                    regra_id, regra_nome, criticidade,
                    franquia_nome, franquia_cod_id,
                    residente_nome, residente_cod_id,
                    comodo_nome, comodo_local, device_id, canais, condicoes_match
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id, disparado_em
                """,
                (
                    log_item.regra_id, log_item.regra_nome, log_item.criticidade,
                    log_item.franquia_nome, log_item.franquia_cod_id,
                    log_item.residente_nome, log_item.residente_cod_id,
                    log_item.comodo_nome, log_item.comodo_local, log_item.device_id,
                    log_item.canais,
                    condicoes_json,
                ),
            )
            row = cur.fetchone()
    return {"success": True, "id": row[0], "disparado_em": row[1].isoformat()}

# ---------------------------------------------------------------------------
# Telefones
# ---------------------------------------------------------------------------

@app.get("/api/alertas/telefones")
def listar_telefones(franquia_cod_id: Optional[str] = None):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if franquia_cod_id:
                cur.execute(
                    "SELECT * FROM lista_telefones_alertas WHERE franquia_cod_id = %s ORDER BY id",
                    (franquia_cod_id,),
                )
            else:
                cur.execute("SELECT * FROM lista_telefones_alertas ORDER BY franquia_cod_id, id")
            rows = cur.fetchall()
    return [dict(r) for r in rows]


@app.post("/api/alertas/telefones", status_code=201)
def criar_telefone(t: TelefoneItem):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO lista_telefones_alertas
                    (franquia_cod_id, franquia_nome, nome_contato, telefone, canal, ativo, regra_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (t.franquia_cod_id, t.franquia_nome, t.nome_contato, t.telefone, t.canal, t.ativo, t.regra_id),
            )
            new_id = cur.fetchone()[0]
    return {"success": True, "id": new_id}


@app.put("/api/alertas/telefones/{telefone_id}")
def atualizar_telefone(telefone_id: int, t: TelefoneItem):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE lista_telefones_alertas
                SET franquia_cod_id = %s, franquia_nome = %s, nome_contato = %s,
                    telefone = %s, canal = %s, ativo = %s, regra_id = %s
                WHERE id = %s
                """,
                (t.franquia_cod_id, t.franquia_nome, t.nome_contato,
                 t.telefone, t.canal, t.ativo, t.regra_id, telefone_id),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Telefone nao encontrado.")
    return {"success": True}


@app.delete("/api/alertas/telefones/{telefone_id}")
def remover_telefone(telefone_id: int):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM lista_telefones_alertas WHERE id = %s", (telefone_id,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Telefone nao encontrado.")
    return {"success": True}

# ---------------------------------------------------------------------------
# Presence Summary
# ---------------------------------------------------------------------------

@app.get("/api/presence/residentes")
def listar_residentes():
    """Retorna pares distintos (residente, comodo) para popular os selects do painel."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT residente, comodo
                FROM presence_summary
                WHERE evento ILIKE 'reporte:%%'
                GROUP BY residente, comodo
                ORDER BY residente, comodo
                """
            )
            rows = cur.fetchall()

    # Agrupa comodos por residente
    mapa: dict = {}
    for r in rows:
        nome = r["residente"]
        comodo = r["comodo"]
        if nome not in mapa:
            mapa[nome] = []
        mapa[nome].append(comodo)

    return [{"residente": k, "comodos": v} for k, v in sorted(mapa.items())]


@app.get("/api/presence/eventos")
def listar_eventos_presence(
    residente: str = Query(...),
    comodo: str = Query(...),
):
    """Retorna eventos de presence_summary para um residente e comodo especificos."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, residente, comodo, area, evento,
                       tempo_inicial, tempo_final
                FROM presence_summary
                WHERE residente = %s
                  AND comodo = %s
                  AND evento ILIKE 'reporte:%%'
                ORDER BY tempo_inicial DESC
                """,
                (residente, comodo),
            )
            rows = cur.fetchall()

    result = []
    for r in rows:
        row = dict(r)
        if row.get("tempo_inicial"):
            row["tempo_inicial"] = row["tempo_inicial"].isoformat()
        if row.get("tempo_final"):
            row["tempo_final"] = row["tempo_final"].isoformat()
        result.append(row)

    return result


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info(f"Iniciando Anglis Alertas API na porta {API_PORT}")
    uvicorn.run(app, host="0.0.0.0", port=API_PORT)
