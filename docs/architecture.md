# Architecture Notes

TradeFrame separates collection strategy from raw data acquisition.

## Boundaries

- `AlecaAdapter` is the only code that reads AlecaFrame paths.
- Repositories own SQLAlchemy persistence.
- Services own business rules and scoring.
- API routes translate service results into typed response DTOs.
- React renders API data and does not calculate collection rules.

## Database

MySQL is a TradeFrame-owned cache and analytics store. AlecaFrame remains the source of truth. A sync can rebuild inventory state from AlecaFrame at any time.

## Encryption

AlecaFrame `lastData.dat` is treated as encrypted text. The adapter contains an AES-CBC decoder with key and IV candidates recovered from the local AlecaFrame DLL string table. If AlecaFrame changes its cryptography, only the adapter should change.
