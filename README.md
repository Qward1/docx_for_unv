# docx_service_for_unv

Отдельная копия сервиса под новую задачу: на вход поступает готовый текст ответа абитуриенту, на выходе формируется `DOCX` по шаблону приемной комиссии.

Сейчас проект подготовлен как независимая ветка разработки рядом с основным сервисом:

- папка проекта: [docx_service_for_unv](/mnt/c/Users/Admin/Desktop/Опять%20работа/docx-service/docx_service_for_unv)
- текущий шаблон МАИ: [shablon_unv.docx](/mnt/c/Users/Admin/Desktop/Опять%20работа/docx-service/docx_service_for_unv/shablon_unv.docx)

Сейчас в проект уже подставлен присланный шаблон `Shablon_dokumenta.docx`. Если позже появится новая версия, её нужно будет просто заменить файлом `shablon_unv.docx`.

## Что уже подготовлено

- сервис запускается отдельно от исходного проекта;
- шаблон вынесен в отдельный файл `shablon_unv.docx`;
- endpoint `/generate` уже умеет принимать не только `text`, но и просто `body_text`;
- служебные маркеры шаблона `{{BODY_ECP}}` и `{{BODY_EXEC}}` при генерации очищаются;
- текущую копию можно дальше упрощать под шаблон приемной комиссии, не ломая основной проект.

## Запуск

```bash
cd "/mnt/c/Users/Admin/Desktop/Опять работа/docx-service/docx_service_for_unv"
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8011
```

## Минимальный запрос

```json
{
  "body_text": "Уважаемый абитуриент! Ваше обращение рассмотрено приемной комиссией..."
}
```

## Следующий шаг

После получения нового `docx`-шаблона нужно будет:

1. заменить `shablon_unv.docx`;
2. отметить в шаблоне места под текст;
3. при необходимости упростить модель данных и убрать неиспользуемые поля от старого сервиса.

## Dify

Готовые материалы для Dify:

- схема узлов: [docs/dify-workflow.md](/mnt/c/Users/Admin/Desktop/Опять%20работа/docx-service/docx_service_for_unv/docs/dify-workflow.md)
- prompt template: [docs/dify-prompt-template.md](/mnt/c/Users/Admin/Desktop/Опять%20работа/docx-service/docx_service_for_unv/docs/dify-prompt-template.md)

## Выгрузка На Сервер

Так как эта папка находится вне старого git-репозитория, самый быстрый способ — скопировать её на сервер отдельно.

С локальной машины:

```powershell
scp -r "C:\Users\Admin\Desktop\Опять работа\docx-service\docx_service_for_unv" jnserver:/root/
```

На сервере:

```sh
cd /root/docx_service_for_unv
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
nohup .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8011 > docx_service_for_unv.log 2>&1 &
echo $! > docx_service_for_unv.pid
```
