# Сравнение форматов хранения данных.

**Задачи:**<br>
1. Взять датасет на 10 ГБ
2. Сохранить его в различных форматах
3. Выполнить различные SQL операции с этими файлами
4. Сделать график

# Подготовка окружения
1. python -m venv .bigdata  
2. .bigdata/Scripts/activate 
3. pip install -r requirements.txt 

# Загрузка датасета
`python take_10gb.py`<br><br>

Я взял датасет комментариев с Реддита: `fddemarco/pushshift-reddit-comments.` <br>
Датсет достаточно большой, поэтому я сделал выгрузку только 10Гб с помощью `take_10gb` 

# Сохраняем в различных форматах
`python scripts/benchmark_write.py`<br><br>

Форматы:
1. .csv
2. .jsonl
3. .orc
4. .parquet
5. .sqlite

*.json обраатывался слишком долго и убивал ядро, поэтому я отказался от него*

# Операции с различными форматами
`python scripts/benchmark_read.py`
Сделал 2 режима:
- direct - Запросы сразу к файлам - `read_parquet(...), read_csv_auto(...)` и.т.п
- materialized - Запросы через CREATE TEMP TABLE<br>

Операции:
1. read - 
```
SQL SELECT count(*) FROM source
```
2. filter - 
```
SELECT count(*)
FROM source
WHERE score > 10 AND subreddit IS NOT NULL
```
3. groupby - 
```
SELECT subreddit, count(*) AS cnt, avg(score) AS avg_score
FROM source
WHERE subreddit IS NOT NULL
GROUP BY subreddit
ORDER BY cnt DESC
LIMIT 100
```
4. window - 
```
SELECT subreddit, author, created_utc, score
FROM (
    SELECT *,
           row_number() OVER (
               PARTITION BY subreddit
               ORDER BY created_utc DESC
           ) AS rn
    FROM source
    WHERE subreddit IS NOT NULL AND created_utc IS NOT NULL
) t
WHERE rn <= 3
```
5. materialize - поддерживает 2 режима: <br>
`direct` — запросы выполняются напрямую над источником данных<br>
`materialized` — данные предварительно загружаются в временную таблицу

# Результаты

Посмотреть все дашборды: выполнить команду `python -m http.server 8000` и перейти на `http://localhost:8000/results/benchmark_dashboard.html`

## Write

![Дашборд записи](image.png)

## Read Direct

![alt text](image-1.png)
![alt text](image-2.png)
