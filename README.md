# Jupiter Swap GUI

A graphical interface for managing token swaps on Solana via the Jupiter Aggregator.

## Features

- Add, edit, and delete token swap pairs
- Import pairs from a file
- Run all swaps with one click
- Monitor token balances
- Store pairs in a SQLite database
- Securely store your private key in a local file

## Requirements

- Python 3.8+
- PyQt5
- `jup_swap` module (must be implemented separately)

## Usage

```bash
pip install -r req.txt
python main.py
```

## Files

- `main.py` — main GUI
- `jup_swap.py` — module for Jupiter Aggregator interaction (not included)
- `pairs.db` — database for pairs (created automatically)
- `private_key.txt` — private key (not added to git)

## Important

- Do not store your private key in public repositories!
- You need a `jup_swap.py` file that implements Solana interaction.

## Contract Descriptions

For contract details and support, visit the Telegram channel: [https://t.me/wwafwt](https://t.me/wwafwt)

## License

MIT
## License

MIT
