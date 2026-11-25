# Jarvis Personal Assistant - stato, decisioni e roadmap

Ultimo aggiornamento: 25 novembre 2026.

## Candidato per revisioni documentali

Implementato un incremento candidato con originali immutabili collegati, If-Match,
risoluzione della revisione corrente e rifiuto delle analisi superate. Migrazione
aggiuntiva 20261125_0007 applicata e verificata sul database di Edith; piloti
esistenti non riavviati.
Lint/formattazione/compilazione e 110 test locali mirati superati. Il collaudo
Linux del commit d9518bb6ba990aeefd79fa6edb7e32b7783403de ha restituito
CANDIDATE_CHECKS=PASS (conteggi non forniti dall'operatore). L'helper ha verificato
passaggio 0006 -> 0007 e vincoli, con guardie su destinazione, TLS, schema e
versione; sei casi locali passati. Avvio del nuovo pilota e collaudo degli endpoint
revisioni con storage reale ancora pendenti.
Evidenza: docs/validation/2026-11-25-revisions-candidate.json.
Contratto, limiti e ripristino: docs/DOCUMENT_REVISIONS.md.

## Collaudo multiutente del 25 novembre

Superata la prova con due account temporanei autenticati sul backend reale:
letture/analisi incrociate negate, cache separata anche con hash identici, viewer
limitato alla lettura e revoca efficace sulla sessione gia aperta. Logout,
revoca sessioni e disattivazione account di test confermati. Documenti sintetici
rimossi dall'app; identita e audit mantenuti. Nessuna nuova inferenza richiesta:
la prova usa analisi sintetiche deterministiche, distinte dai precedenti test AI.
Gli account personali esistenti non sono stati modificati.

Restano aperti aggiornamento dei documenti e invalidazione delle analisi, lifecycle e separazione
delle copie Open WebUI, purge fisico S3, ricerca nell'archivio e verifica degli
strumenti originali/visivi PDF in questo pilota. Il servizio resta interno.
Evidenza: docs/validation/2026-11-25-multiuser-pilot.json.

## Verifica del collegamento Open WebUI del 24 novembre

La chiave dedicata legge il profilo e i tre strumenti. I parametri sono nascosti
agli utenti con sola lettura in Open WebUI 0.13.4: il precedente controllo li
interpretava erroneamente come mancanti. La lettura amministrativa diretta ha
riconfermato think booleano true, contesto 65536 e versione
173da814-b2a7-4aba-9f8a-dc0b1e21ec80, senza modifiche al profilo.
La correzione candidata accetta parametri nascosti soltanto per quella versione
esplicitamente attestata nella configurazione. Il collaudo Linux della nuova
immagine ha superato 92 test (uno saltato); il probe con chiave dedicata e pin
restituisce ok=true. Analisi LLM di un TXT e di un PDF sintetici riuscite; il pilota
precedente resta AI disabled. Il nuovo jarvis-backend-ai-pilot e pronto, con AI
Open WebUI configurata, senza porte pubblicate e con Traefik disabilitato.
L'API amministrativa conferma inoltre ruolo user
per l'unico account chiamato Jarvis App (non identifica la chiave salvata).
Evidenza: docs/validation/2026-11-24-openwebui-candidate.json.

Il primo tentativo AI ha restituito 503 dopo login, upload e verifica originale
riusciti. La chat Open WebUI e stata creata ma e rimasta priva di risposta finale.
Verificato un permesso mancante sul modello base qwen3.8:27b: accesso in lettura
aggiunto al solo utente tecnico e riletto, senza cambiare parametri, versioni o
ruolo. La ripetizione ha restituito 200: codice/scadenza e fonti, dati mancanti,
persistenza, cache sullo stesso originale, blocco anonimo e famiglia errata,
logout/revoca verificati. Il secondo TXT sintetico e stato rimosso dall'app;
quello del tentativo fallito resta conservato. Nessun originale reale modificato.
Anche il PDF sintetico ha restituito 200, con gli stessi controlli su fonti,
identita, persistenza/cache, dati mancanti e accessi superati, poi rimozione
dall'applicazione verificata. Il flusso iniziale e collaudato sui documenti
caricati nell'app, senza attestare ricerca nell'archivio o accesso indiscriminato.
Copie Open WebUI, purge fisico S3, sostituzione
del documento e invalidazione dell'analisi restano da verificare. L'uso effettivo
degli strumenti di lettura/render PDF non e dimostrato da questo solo risultato.
Il servizio resta un pilota interno temporaneo, non un rilascio di produzione.
Il successivo collaudo con due account temporanei sull'API reale, nuclei
distinti, hash identici e grant/revoca viewer e stato superato il 25 novembre,
come riportato sopra.
Procedura, pulizia e limiti: docs/MULTIUSER_PILOT.md.
Dettagli e ripristino: docs/ULTRON_INTEGRATION.md.

## Ripresa del 20 novembre: applicazione e inferenza separate

L'host **jarvis** ospitera l'applicazione; l'host **ultron** esegue LLM, Ollama,
Open WebUI e Docling. `jarvis` e anche il nome del profilo Open WebUI su Ultron.
L'architettura dati del 22 ottobre resta confermata: PostgreSQL 17 e RustFS su
**edith**, con database jarvis, utente jarvis_app e bucket jarvis-documents-prod
dedicati all'applicazione. Nessuna migrazione dei dati sull'host jarvis e prevista.
La precedente annotazione che escludeva Edith era un'interpretazione errata ed e
sostituita da questa conferma dell'utente. Esistenza e permessi delle risorse vanno
verificati prima del primo avvio; non si usano risorse di altre applicazioni.

Su jarvis sono stati verificati tramite output dell'utente Debian 13.7, circa
8 GiB RAM, Traefik healthy sulla rete proxy e la presenza di /opt/jarvis. Al primo
inventario nessun container applicativo era avviato. I file sotto /opt/jarvis puntano
a Edith 10.10.30.20:5432 (TLS require) e 10.10.30.20:9000 (S3 path-style).
Tailscale e attivo su jarvis, IP 100.79.96.2; HTTP verso Open WebUI su Ultron
100.127.56.71:3000 verificato dall'host e da Traefik. Autenticazione API Open WebUI
ancora da verificare; accesso autenticato PostgreSQL e HEAD del bucket verificati.

Il codice locale del ramo feature/ultron-document-analysis aggiunge il provider
Open WebUI, senza aggiornare il profilo remoto o cambiare i contratti Android.
Endpoint Tailscale esplicito, allegato singolo, nuova chat per analisi, native
tool calling, ragionamento booleano attivo e risultato JSON finale validato.
Nessun fallback cloud. La configurazione di rilascio e candidata e non applicata.

Verifica successiva sul container Linux di Jarvis: immagine preflight-9116880
costruita dal commit 911688036092399e77f1d1ff1577ee17bcae3de4; preflight ok=true.
Autenticazione PostgreSQL e TLS effettivo confermati, privilegi sullo schema
disponibili; HEAD del bucket S3 riuscito. Database senza tabelle applicative e
senza tabella Alembic. La suite completa Linux sul candidato ha poi restituito
82 passed, 1 skipped e CANDIDATE_CHECKS=PASS; lint, formattazione e compilazione
superati. Successivamente l'utente ha applicato le sei migrazioni dall'immagine
verificata su Jarvis al database jarvis su Edith: alembic current conferma
20261022_0006 (head). Lettura/scrittura oggetti ancora da verificare; primo
account e pilota interno predisposti come descritto sotto.

Primo proprietario creato tramite CLI interattiva; nessuna credenziale o identita
personale viene registrata qui. Container jarvis-backend-pilot avviato sulla rete
proxy con traefik.enable=false, nessuna porta host, AI disabled. L'endpoint interno
/health/ready restituisce ready con PostgreSQL e object_storage available. Smoke
autenticato riuscito: rifiuto anonimo, login, identita, nucleo owner e persona
collegata, logout e revoca confermati. Smoke documentale riuscito: TXT sintetico
caricato, hash e byte originali verificati, accessi anonimi respinti, nucleo e
documento inesistenti nascosti, analisi AI disabilitata e solo file sintetico
rimosso. Lettura/scrittura via S3 confermata attraverso l'API applicativa;
isolamento fra due utenti reali e analisi AI live ancora da collaudare.

Configurazione, prove, limiti di conservazione delle copie su Open WebUI, gestione
dei job lunghi e ripristino sono in [ULTRON_INTEGRATION.md](ULTRON_INTEGRATION.md).
La baseline locale di partenza e 02edf87 sul ramo develop, confrontata con la
testa remota dello stesso ramo prima della pubblicazione: coincidono. L'incremento
e pubblicato nella PR #11 in bozza verso develop. Nessun merge o rilascio
permanente; l'avvio del solo pilota interno e descritto sopra.

## Stato storico al 22 ottobre 2026

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

La tecnologia Android è Kotlin con Jetpack Compose. La prima build nativa usa Android Keystore
per cifrare le sessioni, il selettore documenti del sistema e networking HTTPS diretto. Cache
locale, biometria e WorkManager restano incrementi successivi al primo APK installabile.

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

- 21 test automatici superati e un test PostgreSQL d'integrazione disponibile su richiesta.
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
- Percorso MVP end-to-end verificato su PostgreSQL 17.11 e RustFS 1.0.1 reali in Docker,
  includendo analisi documentale strutturata contro un simulatore API locale, tracciabilità della
  fonte, cancellazione a cascata, attività, rotazione della sessione e logout.
- Nessuna connessione o modifica è stata effettuata sulle VM di produzione.
- Preparato il Compose di produzione aderente al contratto Jarvis/Edith, senza porte host.
- Preparata la pubblicazione GHCR su aggiornamenti di `main`, con digest riportato nel riepilogo.

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
- [x] endpoint di lettura dei nuclei e gestione dei profili persona;
- [x] controlli autorizzativi `owner`/`adult`/`viewer` e isolamento fra nuclei;
- [x] audit minimo persistente di login, refresh e logout, senza credenziali in chiaro;
- [x] limiti in memoria ai tentativi di autenticazione per client e account, adeguati alla
  singola istanza prevista dall'MVP e senza introdurre nuovi servizi.

### Incremento 3 - documenti

- [x] upload autenticato dall'app Android tramite body HTTP;
- [x] convalida formato, limite 25 MiB, nome sicuro e hash SHA-256;
- [x] object key isolata per nucleo e documento;
- [x] metadati in PostgreSQL e originale privato in RustFS;
- [x] download mediato dal backend dopo autorizzazione, senza esporre RustFS;
- [x] cancellazione coordinata tra database e RustFS;
- [x] conservazione dell'originale;
- modello per testo estratto, fonte e versione dell'analisi.

### Incremento 4 - comprensione e pratiche

- [x] pipeline sincrona attivata su richiesta, senza coda esterna;
- [x] riassunto semplice e dati estratti con evidenza della fonte;
- [x] separazione esplicita fra originale, fatti osservati e suggerimenti;
- pratiche, checklist, attività, scadenze e appuntamenti collegati;
- stato `proposto` prima della conferma per le azioni rilevanti;
- [x] primo flusso verticale: documento -> riassunto -> scadenze -> azioni confermate in Oggi.

### Nucleo operativo "Oggi"

- [x] attività isolate per nucleo;
- [x] priorità `low`, `normal`, `high`, `urgent`;
- [x] scadenza opzionale e ordinamento per urgenza/data;
- [x] assegnazione opzionale a persona e collegamento a documento dello stesso nucleo;
- [x] completamento e storico delle attività concluse;
- [x] permessi di modifica limitati a proprietari e adulti;
- [ ] promemoria e notifiche Android conservative.

### Incremento 5 - Android MVP

- [x] accesso con sessione cifrata in Android Keystore e refresh automatico;
- [ ] sblocco biometrico locale;
- [x] schermata Oggi con elenco, creazione rapida e completamento attività;
- prossimi appuntamenti e scadenze;
- chat testuale;
- [x] acquisizione PDF/immagine/testo e upload;
- [x] dettaglio immediato con riassunto, scadenze, dati mancanti e azioni proposte;
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

La v0.1 è una release candidate installabile. Il prossimo passo è la promozione controllata da
`develop` a `main`, che richiede approvazione esplicita, seguita da pubblicazione GHCR, installazione
per digest, migrazioni e smoke test sulle VM reali. I prerequisiti e le evidenze sono raccolti in
`docs/releases/0.1.0-rc1.md`.

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
| 22/10/2026 | Aggiunti profili del nucleo, ruoli applicativi e test di isolamento multi-tenant. |
| 22/10/2026 | Implementato il ciclo documenti privati PostgreSQL/RustFS con hash e autorizzazione. |
| 22/10/2026 | Preparato il pacchetto Compose, verifica immagine, rilascio e rollback per Public-Jarvis. |
| 22/10/2026 | Implementate le attività della schermata Oggi con priorità, scadenze e collegamenti. |
| 22/10/2026 | Creato e compilato il primo APK Android nativo con login, Oggi e upload documenti. |
| 22/10/2026 | Superato il collaudo end-to-end dell'MVP su PostgreSQL e RustFS reali; corretta la tipizzazione SQL degli aggiornamenti attività. |
| 22/10/2026 | Aggiunti audit persistente dell'autenticazione, limiti ai tentativi di accesso e gestione sicura degli header del proxy. |
| 22/10/2026 | Completato il flusso Android Oggi con creazione rapida delle attività; APK ricompilato e firma v2 verificata. |
| 22/10/2026 | Completato il flusso documento → spiegazione → azioni confermate, con output strutturato e fonti. |

## Vincoli operativi del repository

- Commit, push e merge verso `develop` sono autorizzati per il completamento autonomo dell'MVP.
- La promozione o il deployment di `main` richiedono conferma esplicita sul rilascio pronto.
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
