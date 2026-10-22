# Jarvis Personal Assistant - stato, decisioni e roadmap

Ultimo aggiornamento: 22 ottobre 2026.

Questo documento raccoglie in un solo punto gli avanzamenti, le idee, le decisioni e i
prossimi sviluppi. Deve essere aggiornato a ogni modifica funzionale o architetturale
significativa. Le modifiche all'infrastruttura operativa devono essere riportate anche nel
documento infrastrutturale mantenuto separatamente, senza includere credenziali.

## Visione

Jarvis è una segretaria digitale personale e familiare. Il principio guida è: **l'utente
parla o carica un contenuto; Jarvis lo organizza**. Il sistema deve ridurre il carico di
memoria, mantenere il filo delle attività e mostrare ciò che serve nel momento giusto.

Jarvis riceverà testo, voce, fotografie, PDF, screenshot ed email e li trasformerà in:

- spiegazioni semplici;
- attività e checklist;
- scadenze e appuntamenti;
- documenti e informazioni ricercabili;
- suggerimenti e promemoria contestuali.

Le azioni vincolanti restano sotto il controllo dell'utente. Invii, firme, pagamenti,
prenotazioni e decisioni importanti richiedono una conferma esplicita.

## Ambito funzionale

Le aree previste dal progetto sono:

- chat e voce con linguaggio naturale;
- acquisizione e conservazione di documenti originali;
- estrazione di date, orari, luoghi, persone, importi, scadenze e azioni;
- pratiche con stato, checklist, documenti, attività e appuntamenti collegati;
- analisi delle email e preparazione di bozze;
- calendario personale e familiare, inclusi luogo e tempo di partenza;
- pagamenti, ricorrenze e stato pagato/non pagato;
- memoria organizzativa persistente e separata per ciascuna persona;
- priorità: oggi, questa settimana, urgente, importante, può aspettare;
- ripresa delle attività aperte dopo un periodo di assenza.

L'autonomia desiderata è inizialmente pari a 7/10: Jarvis può proporre spontaneamente, ma
non deve eseguire azioni importanti senza controllo umano.

## Utenti, famiglia e isolamento dei dati

Jarvis è progettato fin dall'inizio come applicazione multiutente, pur partendo da un MVP
personale. Il modello scelto distingue:

- `users`: account che possono autenticarsi;
- `households`: spazio familiare o organizzativo condiviso;
- `household_memberships`: appartenenza e ruolo dell'account nello spazio;
- `people`: persone gestite nello spazio, anche prive di un proprio account;
- `auth_sessions`: sessioni revocabili, memorizzate soltanto come token hash.

Questo consente a un adulto di gestire profili separati per i figli, mantenendo documenti e
memoria distinti, e permette in futuro a più adulti di collaborare nello stesso nucleo.
Ogni futura tabella applicativa dovrà essere riconducibile a un `household_id` e, quando
necessario, a un `person_id`. L'autorizzazione deve essere verificata nel backend per ogni
richiesta; l'interfaccia non è un confine di sicurezza.

Ruoli iniziali previsti: `owner`, `adult`, `viewer`. Permessi più granulari saranno aggiunti
solo quando emergerà un caso d'uso concreto.

## Piattaforme

- Android è il client principale dell'MVP.
- L'uso da Mac sarà supportato da un'interfaccia web responsiva o da un client successivo,
  basato sulle stesse API.
- Il backend resta indipendente dal client e predisposto a future integrazioni con
  WhatsApp o Telegram.
- Le funzioni sensibili nell'app Android dovranno poter essere protette con biometria o PIN
  e usare lo storage sicuro del sistema per le credenziali locali.

Tecnologia Android ancora da confermare prima dell'implementazione. La scelta proposta è
Kotlin con Jetpack Compose, networking HTTP, database locale per cache controllata e
WorkManager per sincronizzazioni differibili. La decisione diventerà vincolante soltanto
dopo una breve prova tecnica su acquisizione documenti, autenticazione biometrica e
notifiche.

## Infrastruttura confermata

L'infrastruttura è già operativa e costituisce un vincolo del progetto:

- backend Docker sulla VM Jarvis, dietro Traefik;
- PostgreSQL 17 sulla VM Edith per dati strutturati, relazioni, stato e metadati;
- RustFS S3-compatible sulla VM Edith per documenti e oggetti persistenti;
- bucket privato `jarvis-documents-prod`, accesso path-style;
- TLS obbligatorio per PostgreSQL;
- nessuna porta del backend pubblicata direttamente sull'host;
- reti Docker esterne `proxy` e `jarvis-app`;
- backend stateless in ascolto interno su `0.0.0.0:8080`;
- filesystem del container in sola lettura e `/tmp` temporaneo;
- immagini e dipendenze di produzione fissate a versioni o digest verificati.

Lo storage S3-compatible locale è adeguato anche in modalità multiutente: gli oggetti
saranno separati tramite chiavi che includono l'identificativo del nucleo, mentre
PostgreSQL conserverà proprietà, autorizzazioni, hash, tipo MIME, dimensione e stato di
elaborazione. Il bucket non sarà esposto pubblicamente. Eventuali URL temporanei dovranno
essere generati solo dopo il controllo autorizzativo. Se il carico crescerà, l'interfaccia
S3 consentirà di valutare un servizio Hetzner esterno senza cambiare il modello applicativo.

Non sono previsti Redis, code, database aggiuntivi o orchestratori nell'MVP.

## Stack backend iniziale

- Python 3.12;
- FastAPI per API HTTP e contratti OpenAPI;
- SQLAlchemy e psycopg per PostgreSQL;
- Alembic per migrazioni esplicite;
- boto3 per l'API S3-compatible di RustFS;
- Uvicorn come server ASGI;
- pytest per i test;
- Ruff per qualità e formattazione.

Le dipendenze runtime del container sono registrate con versioni esatte in
`requirements.lock`. L'immagine base del container deve essere fornita tramite riferimento
immutabile con digest al momento della build.

## Avanzamenti completati

### Analisi e impostazione

- Letto il documento funzionale originario e recepiti i principi di prodotto.
- Letta integralmente l'architettura del datacenter pubblico.
- Verificato il repository GitHub pubblico: al controllo iniziale risultava accessibile e
  vuoto.
- Creato un repository Git locale di lavoro sul ramo `main`, senza commit e senza push.
- Definito il primo ADR sullo stack backend.

### Backend eseguibile

- Creata la struttura Python installabile.
- Implementato `GET /health/live`, indipendente dai servizi esterni.
- Implementato `GET /health/ready`, negativo se PostgreSQL o RustFS non sono disponibili.
- Implementato `GET /api/v1/version`.
- Aggiunti log JSON e identificativo di correlazione per richiesta.
- Evitata l'esposizione nei log di password, credenziali S3 e stringhe di connessione.
- Configurata la lettura della password PostgreSQL da file montato.
- Aggiunti client di controllo per PostgreSQL e bucket S3.
- Aggiunto uno smoke test per gli endpoint e le dipendenze.

### Dati e container

- Creata la prima migrazione Alembic per utenti, nuclei, appartenenze, persone e sessioni.
- Preparato un Dockerfile con utente non privilegiato, porta interna 8080 e arresto
  controllato entro il limite infrastrutturale.
- Verificato e fissato il digest dell'immagine base Python 3.12 slim.
- Aggiunti `.dockerignore`, esempio di configurazione e contratto di deployment/rollback.
- Resa esplicita e separata dall'avvio normale l'esecuzione delle migrazioni.

### Verifiche locali

- 9 test automatici superati e un test PostgreSQL d'integrazione disponibile su richiesta.
- Controlli Ruff e formattazione superati.
- Compilazione dei moduli Python superata.
- SQL della migrazione generato offline correttamente per PostgreSQL.
- Immagine backend costruita con successo tramite Docker Desktop.
- Smoke test dell'immagine superato con utente `10001:10001`, root filesystem in sola
  lettura, capability rimosse, `no-new-privileges`, limiti di CPU/memoria/PID e nessuna
  porta host pubblicata.
- Nel container, liveness e versione rispondono `200`; senza dipendenze configurate la
  readiness risponde correttamente `503` senza esporre dettagli sensibili.
- Autenticazione verificata con test unitari/API e con un ciclo completo su PostgreSQL 17.11
  temporaneo: migrazioni, creazione proprietario, login, refresh atomico e revoca.
- Nessuna connessione o modifica è stata effettuata sulle VM di produzione.

## MVP proposto

### Incremento 1 - fondamenta tecniche (completato localmente)

- configurazione sicura;
- logging e correlazione richieste;
- health endpoint;
- connessione PostgreSQL e RustFS;
- modello identità multiutente iniziale;
- container non privilegiato;
- test e smoke test.

### Incremento 2 - autenticazione e nucleo familiare

- [x] creazione amministrativa e non pubblica del primo proprietario;
- [x] login, refresh e logout con rotazione atomica delle sessioni;
- [x] hashing password Argon2id;
- [x] token opachi salvati in PostgreSQL esclusivamente come hash;
- [x] creazione atomica del primo nucleo e del profilo persona collegato;
- [x] endpoint autenticato `GET /api/v1/me`;
- [ ] endpoint di gestione dei profili del nucleo;
- [ ] controlli autorizzativi per nucleo/ruolo sulle risorse applicative;
- audit minimo degli eventi di sicurezza;
- limiti alle richieste di autenticazione senza introdurre nuovi servizi.

### Incremento 3 - documenti

- upload diretto dall'app Android;
- convalida formato, dimensione e hash;
- object key isolata per nucleo e documento;
- metadati e stato di elaborazione in PostgreSQL;
- download autorizzato e cancellazione coordinata tra database e RustFS;
- conservazione dell'originale;
- modello per testo estratto, fonte e versione dell'analisi.

### Incremento 4 - comprensione e pratiche

- pipeline inizialmente sincrona o attivata su richiesta, senza coda esterna;
- riassunto semplice e dati estratti con evidenza della fonte;
- separazione esplicita fra testo originale, interpretazione e suggerimento;
- pratiche, checklist, attività, scadenze e appuntamenti collegati;
- stato `proposto` prima della conferma per le azioni rilevanti;
- primo flusso verticale: documento importante -> riassunto -> scadenze -> checklist.

### Incremento 5 - Android MVP

- accesso e sblocco biometrico;
- schermata Oggi con poche priorità;
- prossimi appuntamenti e scadenze;
- chat testuale;
- acquisizione foto/PDF e avanzamento upload;
- dettaglio documento con riassunto, dati estratti e azioni proposte;
- schermata "Cosa devo fare?";
- notifiche locali iniziali, con regole conservative.

### Incremento 6 - prove reali e integrazioni

- calendario;
- importazione e analisi email con permessi minimi;
- voce;
- bozze di risposta;
- affinamento delle notifiche sulla base dell'uso reale;
- solo in seguito, valutazione di messaggistica e automazioni più autonome.

## Modello dati successivo

Entità previste dopo le fondamenta identità:

- `documents` e `document_versions`;
- `document_extractions` con fonte e confidenza;
- `cases` o `practices`;
- `tasks` e `checklist_items`;
- `deadlines`;
- `appointments`;
- `payments` e ricorrenze;
- `reminders` e preferenze di notifica;
- `messages` e conversazioni;
- `audit_events` per eventi sensibili.

Le tabelle saranno aggiunte per incrementi verticali, non tutte in anticipo.

## Regole di sicurezza applicativa

- Nessuna credenziale o contenuto personale nei log.
- Accesso agli oggetti soltanto dopo verifica di account, nucleo e ruolo.
- Token di sessione salvati lato server solo sotto forma di hash.
- Validazione di tipo, dimensione e nome dei file caricati.
- Cancellazione definitiva progettata come operazione esplicita, tracciabile e coerente fra
  PostgreSQL e RustFS.
- Nessuna informazione mancante deve essere inventata, soprattutto per questioni legali,
  sanitarie o finanziarie.
- Ogni proposta AI deve distinguere dati osservati, interpretazioni e suggerimenti.
- Le azioni esterne vincolanti richiedono conferma finale.

## Decisioni aperte

- Regole e intensità delle notifiche.
- Confine preciso fra creazione automatica, bozza e conferma.
- Provider e modalità di integrazione per email e calendario.
- Modelli AI, criteri di routing, privacy e limiti di costo.
- Politica di conservazione, esportazione e cancellazione dei dati.
- Secondo fattore di autenticazione e recupero account.
- Tecnologia Android definitiva dopo la prova tecnica.
- Strategia di elaborazione in background quando i carichi reali supereranno il modello
  semplice dell'MVP.

## Prossimo passo consigliato

Implementare l'incremento 2 con un flusso completo e testato:

1. creazione del primo account e del nucleo;
2. login e refresh sessione;
3. endpoint per leggere e modificare i profili del nucleo;
4. autorizzazione basata su appartenenza e ruolo;
5. test di isolamento: un utente non deve poter accedere a dati di un altro nucleo.

Prima del primo deployment saranno inoltre necessari il digest verificato dell'immagine base,
la build dell'immagine applicativa, la convalida del Compose esistente, l'esecuzione esplicita
della migrazione e lo smoke test contro l'ambiente reale.

## Registro sintetico

| Data | Avanzamento |
| --- | --- |
| 22/10/2026 | Acquisiti requisiti funzionali, Android come client principale e predisposizione multiutente. |
| 22/10/2026 | Confermata l'architettura PostgreSQL + RustFS S3-compatible su VM dedicate. |
| 22/10/2026 | Creato localmente lo scheletro backend, la migrazione identità, il container e i test. |
| 22/10/2026 | Superati test, lint, formattazione, compilazione e generazione SQL offline. |
| 22/10/2026 | Build e smoke test del container completati tramite Docker Desktop. |
| 22/10/2026 | Implementate sessioni opache, Argon2id, login, refresh, logout e bootstrap proprietario. |
| 22/10/2026 | Migrazioni e ciclo autenticazione verificati su PostgreSQL 17.11 temporaneo. |

## Vincoli operativi del repository

- Nessun commit, push o merge senza autorizzazione esplicita dell'utente.
- Nessun segreto, documento personale o file `.env` reale nel repository.
- Le decisioni irreversibili o le nuove tecnologie devono essere motivate e discusse prima
  dell'adozione.

## Strategia Git

- `main` rappresenta esclusivamente la versione pronta per la produzione.
- `develop` raccoglie le feature integrate in attesa di promozione.
- Le feature vengono sviluppate su branch brevi derivati da `develop`.
- La promozione avviene tramite pull request da `develop` a `main`.
- Le GitHub Actions sono limitate alle pull request verso `main` e agli aggiornamenti di
  `main`; non vengono avviate sui push a `develop` o ai branch feature.
