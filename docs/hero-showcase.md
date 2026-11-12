# Главный баннер

Шаблон главного экрана находится в templates/components/campus_hero.html.
Справа две колонки с примерами сообщений из showcase_messages.html. Карточки
двигаются в противоположных направлениях. Повторы скрыты от скринридеров.

Кнопки слегка следуют за мышью в пределах своей области. Голубая надпись
«ДоскаСВФУ» слегка растягивается при перетаскивании и покачивается при нажатии.
Фон однотонный синий, а жёлтая лента движется внизу баннера. Анимации приостанавливаются,
когда баннер уходит за экран, вкладка скрыта или включена пауза. Системная
настройка и настройка профиля для уменьшения движения также учитываются.

## Фотографии

Файлы остались в ads/static/ads/img/showcase/. Фото доступны по
[лицензии Unsplash](https://unsplash.com/license).

- [Книги и наушники — Kelly Sikkema](https://unsplash.com/photos/a-book-headphones-and-pen-on-a-table-_TyH3BiJSgQ)
- [Студенты за столом — Sanket Mishra](https://unsplash.com/photos/a-group-of-people-sitting-around-a-wooden-table-LCwo5opgr9M)
- [Чипсы из предыдущей версии — Gary Tamin](https://unsplash.com/photos/a-white-bowl-filled-with-chips-on-top-of-a-white-table-Z2C-yghfQMc)

Другие фотографии из предыдущей версии сохранены локально в уменьшенном размере в WebP.

- [Шоколад — André Karwath (Aka), фон изменил nagualdesign](https://commons.wikimedia.org/wiki/File:Chocolate_(blue_background).jpg), [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/).
- [Стакан колы — pic_p_ter](https://commons.wikimedia.org/wiki/File:Glass_cola.jpg), общественное достояние.

## Раздел «Продукты»

В templates/components/food_hero.html текст следует за волной ленты внутри
одного SVG. Перетаскивание задаёт направление и скорость прокрутки. С клавиатуры её можно сдвигать
стрелками. При уменьшении движения остаётся ручной сдвиг без автопрокрутки
и инерции. Кнопки используют то же притяжение к курсору, что и главный баннер.
