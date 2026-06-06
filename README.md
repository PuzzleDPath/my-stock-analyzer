# my-stock-analyzer

A tool for analyzing stock data.

## Features

- Fetch historical stock prices
- Calculate moving averages
- Visualize trends

## Getting Started

```bash
pip install -r requirements.txt
python main.py
```

## Usage

```python
from analyzer import StockAnalyzer

analyzer = StockAnalyzer("AAPL")
analyzer.plot_moving_average(window=20)
```

## License

MIT
