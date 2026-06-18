-- Migracao 004: tabela de acoes registradas por operadores sobre alertas
-- Data: 2026-06-18

CREATE TABLE IF NOT EXISTS acoes_alertas (
    id            SERIAL PRIMARY KEY,
    log_id        INTEGER NOT NULL REFERENCES logs_alertas(id) ON DELETE CASCADE,
    tipo          TEXT NOT NULL CHECK (tipo IN ('atendimento', 'resolucao', 'ignorar')),
    descricao     TEXT NOT NULL,
    usuario       TEXT,
    registrado_em TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_acoes_alertas_log_id ON acoes_alertas(log_id);
