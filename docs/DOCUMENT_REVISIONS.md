# Revisioni immutabili dei documenti

25 novembre 2026. Immagine candidata costruita e collaudata sul server con
CANDIDATE_CHECKS=PASS, commit d9518bb6ba990aeefd79fa6edb7e32b7783403de. I conteggi
pytest non sono stati forniti e non vengono dedotti. Implementazione non ancora
avviata come applicazione; migrazione non ancora applicata.
Il pilota corrente resta jarvis-backend:pilot-5b8e977 e il database verificato
resta alla revisione 20261022_0006. Nessuna migrazione eseguita da questo incremento.

## Decisione e comportamento

Ogni aggiornamento crea un nuovo documento con ID, hash e object key propri,
collegato al precedente nella stessa famiglia. Il predecessore non viene
sovrascritto, rinominato o eliminato. Le analisi precedenti restano nel database
associate al loro originale; non diventano analisi della nuova revisione.
Gli eventuali task collegati al vecchio ID conservano il riferimento storico.
Questo e il versionamento dei documenti caricati nell'app, non sincronizzazione
automatica di file modificati direttamente su S3 o in un altro archivio.

La migrazione aggiuntiva 20261125_0007 crea document_revisions con un solo
successore per predecessore, un solo predecessore per successore e foreign key
composte che impediscono collegamenti fra nuclei. Non riscrive righe documents
o oggetti S3. Il lock timeout DDL e limitato a cinque secondi.

Due aggiornamenti concorrenti bloccano la riga del predecessore: uno solo puo
creare il successore. Solo il nuovo oggetto di una transazione sicuramente
perdente viene eliminato. Se l'esito di persistenza e ambiguo, il candidato resta
conservato, si registra solo il nuovo ID e si restituisce 503 senza errori DB o
parametri privati. Il client deve risolvere la revisione corrente prima di
ritentare; non deve ripetere alla cieca l'upload. Potrebbero rimanere oggetti non
referenziati in caso di errore: la riconciliazione/pulizia non e inclusa qui.

## Contratto API

Tutti i percorsi partono da /api/v1/households/{household_id}/documents.

| Operazione | Risultato |
|---|---|
| POST /{id}/revisions | Nuovo originale, body binario, X-Filename e Content-Type. If-Match obbligatorio, un unico SHA-256 fra virgolette. Risposta 200 con metadata ed ETag della revisione. |
| GET /{id}/revisions/current | Risolve l'ID corrente da una revisione della catena; metadata ed ETag. |
| GET /{id}/revisions | Metadata della catena, ordinati per data di creazione; gli originali si recuperano dai rispettivi ID. |
| GET /{id}/content | Conserva l'accesso all'originale specifico, anche storico, con ETag. Verifica dimensione e hash dei byte letti. |
| GET raccolta documenti | Mostra soltanto gli elementi non superati da un successore. |
| POST /{id}/analysis e GET /{id}/analysis/latest | Per ID superato restituiscono 409; per la nuova revisione nessuna analisi precedente viene riutilizzata. La risposta include source_sha256. |
| DELETE /{id} | Rimane consentito per documenti isolati. Un documento collegato a revisioni restituisce 409 senza eliminare originali. |

If-Match mancante restituisce 428; formato non valido 422; hash non corrispondente
412; predecessore gia superato/concorrenza 409. Contenuto e metadata invariati
sulla revisione corrente restituiscono lo stesso documento senza duplicazione.
Owner e adult possono creare revisioni, viewer puo solo consultare metadata e
originali. Nuclei estranei restano nascosti con 404.

L'analisi ricontrolla la revisione corrente prima di restituire una cache, dopo
l'inferenza e dopo la persistenza. Un aggiornamento osservato durante l'inferenza
produce conflitto anziche una risposta presentata come attuale. Le risposte sono
snapshot riferiti a document_id/source_sha256, non garanzia che un altro utente
non aggiorni il documento dopo la risposta. La lettura latest controlla anche
che l'hash dell'analisi corrisponda all'originale selezionato.

Le cancellazioni dei documenti isolati eseguono prima la transazione DB/FK, poi
la rimozione dell'oggetto: una revisione concorrente non puo lasciare un record
conservato senza originale per una cancellazione anticipata su S3. Un errore S3
successivo puo lasciare un oggetto non referenziato; non viene attestato il purge
fisico delle versioni S3. La cancellazione di un'intera catena, la consultazione
API delle analisi storiche e l'interfaccia di aggiornamento non sono ancora
incluse. Non aggirare il 409 cancellando manualmente i collegamenti.

## Verifiche e collaudo ancora necessario

- Lint, formattazione e compilazione locali superati.
- 110 test locali mirati superati, inclusi dodici casi nuovi del servizio:
  conservazione degli originali, invalidazione corrente, idempotenza, conflitti,
  esito commit ambiguo, modifica durante inferenza/cache, hash errato, ruoli e
  protezione dalla cancellazione della catena.
- Quattro test HTTP tramite ASGI e un test DDL PostgreSQL offline inclusi nel
  collaudo Linux riuscito; non erano risultati locali gia verificati.
- Non ancora verificati sul server migrazione, concorrenza PostgreSQL effettiva,
  nuovi endpoint con S3 reale e nuova inferenza dopo revisione.

Prima costruire la nuova immagine e usare scripts/validate_image.py nel container
temporaneo senza credenziali del database (passaggio completato). I piloti esistenti restano attivi.
Dopo esito verde: leggere alembic current, applicare upgrade head da Jarvis con
la configurazione PostgreSQL esistente e verificare 20261125_0007 (head). Avviare
un nuovo pilota interno distinto e provare solo revisioni sintetiche. Non fare
deployment pubblico o migrazioni sulla VM Ultron.

scripts/migrate_document_revisions.py prepara questo passaggio senza accesso a
S3 o AI. Richiede la destinazione Edith gia verificata, database jarvis, ruolo
jarvis_app, public e TLS require effettivo. Le letture preliminari/finali sono in
transazioni read-only. Solo stato 0006 senza tabella revisioni consente upgrade;
0007 gia applicato esegue soltanto la verifica. Altri stati interrompono il flusso.
Dopo il comando Alembic verifica revisione e nomi dei sei vincoli attesi. Gli
errori grezzi del database non vengono stampati. Sei casi locali del controllo
sono passati; l'helper non e ancora stato eseguito contro il server.

## Ripristino

Conservare le immagini precedenti e gli originali. Il ripristino del precedente
pilota non richiede downgrade: la tabella aggiuntiva puo rimanere intatta.
L'immagine precedente non conosce la catena e puo elencare anche gli ID storici;
usarla solo per diagnostica riferita a ID espliciti, senza affermare quale sia la
revisione corrente. Non cancellare da essa documenti coinvolti in revisioni.
Il downgrade della migrazione rifiuta l'operazione quando esistono collegamenti,
per non perdere la provenienza. Nessun rollback o downgrade eseguito ora.

Rimangono separati lifecycle delle copie Open WebUI, ricerca testuale/semantica,
invalidazione per cambio provider/modello/prompt e strumenti PDF visivi. Il pin
del profilo jarvis, think booleano true e contesto 65536 non sono stati modificati.
