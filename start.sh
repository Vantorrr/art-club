#!/bin/bash

# Запускаем webhook сервер в фоне
python main.py webhook &

# Запускаем бота на переднем плане
python main.py
