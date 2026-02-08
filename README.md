# Monitoramento Inteligente

Teste técnico - Monitoramento Tecnologia

Sistema de ingestão de eventos de câmeras com processamento de regras de alerta, persistência local e interface de monitoramento em tempo real.

## Como Executar

**API** (porta 8000)

```bash
cd api
pip install -r requirements.txt
uvicorn main:app --reload
```
ou

Powershell e CMD:
cd api && pip install -r requirements.txt && uvicorn main:app --reload

**Frontend** (porta 5173)

```bash
cd frontend
npm install
npm run dev
```
ou

Powershell e CMD:
cd frontend && npm install && npm run dev

## Endpoint

`POST /event`

```json
{
  "camera_id": "CAM-01",
  "event_type": "queda",
  "timestamp": 1700000000
}
```

Tipos aceitos: `movimento`, `parado`, `queda`, `inatividade_prolongada`, `invasao_perimetro`.

Regra de Alerta: Eventos de ``queda`` ou ``inatividade_prolongada`` retornam automaticamente `"alert": true`.

Persistência: Os dados são salvos em SQLite para persistência entre reinicializações.

Observabilidade: Logs de operações e erros são gravados em api/app.log.

Documentação: Swagger interativo disponível em `/docs` após iniciar a API.

## Raciocinio Arquitetural

Para um cenário de produção com alta escala, a abordagem ideal seria uma arquitetura assíncrona baseada em eventos. Em vez do módulo de visão computacional realizar chamadas HTTP síncronas para a API de gerenciamento, ele publicaria as detecções em um Message Broker (como Kafka ou RabbitMQ), garantindo o desacoplamento e a resiliência do sistema.

No lado da persistência, o SQLite seria substituído por um banco de dados como PostgreSQL com a extensão TimescaleDB, otimizada para dados de série temporal. Para observabilidade centralizada, utilizaria a stack Grafana Loki ou ELK. Os alertas críticos seriam processados por workers assíncronos (via Celery), que disparariam notificações push via Firebase (FCM). Dessa forma, o fluxo principal de ingestão nunca ficaria bloqueado aguardando integrações externas ou serviços de notificação.

## Implementação própria (Diferencial)

Diferenciais:

Interface inspirada na identidade visual institucional da Monitoramento/AME.

Validação rigorosa de dados com Enums no Pydantic.

Tratamento de estados no frontend (Loading/Error/Success).
