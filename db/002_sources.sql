-- Seed RSS-источников: YouTube Shorts watchlist (EN / RU / ZH).
-- Безопасно для повторного запуска: существующий url пропускается.
-- Плейсхолдер {CHANNEL_ID} удаляется, если остался.

DELETE FROM sources
WHERE url = 'https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}';

INSERT INTO sources (label, url, kind, enabled)
SELECT v.label, v.url, 'rss', true
FROM (VALUES
  ('EN · MrBeast (@MrBeast)', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCX6OQ3DkcsbYNE6H8uQQuVA'),
  ('EN · Zach King (@zachking)', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCq8DICunczvLuJJq414110A'),
  ('EN · How Ridiculous (@HowRidiculous)', 'https://www.youtube.com/feeds/videos.xml?channel_id=UC5f5IV0Bf79YLp_p9nfInRA'),
  ('EN · Dude Perfect (@DudePerfect)', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCRijo3ddMTht_IHyNSNXpNQ'),
  ('EN · 5-Minute Crafts (@5MinuteCraftsYouTube)', 'https://www.youtube.com/feeds/videos.xml?channel_id=UC295-Dw_tDNtZXFeAPAW6Aw'),
  ('EN · MrBeast Gaming (@MrBeastGaming)', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCIPPMRA040LQr5QPyJEbmXA'),
  ('EN · NBA (@NBA)', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCWJ2lWNubArHWmf3FIHbfcQ'),
  ('RU · A4 (@A4a4a4a4)', 'https://www.youtube.com/feeds/videos.xml?channel_id=UC2tsySbe9TNrI-xh2lximHA'),
  ('RU · Wylsacom (@wylsacom)', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCt7sv-NKh44rHAEb-qCCxvA'),
  ('RU · TheBrianMaps (@TheBrianMaps)', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCyJrhZm9KXrzRub3-wD2zWg'),
  ('RU · Маша и Медведь (@MashaBearRUSSIAN)', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCRv76wLBC73jiP7LX4C3l8Q'),
  ('ZH · 李子柒 Liziqi (@cnliziqi)', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCoC47do520os_4DBMEFGg4A'),
  ('ZH · Hua Zi Couple (@huazicouple)', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCKfYEpS4XCoJI0Gb2gWCBvQ')
) AS v(label, url)
WHERE NOT EXISTS (
  SELECT 1 FROM sources s WHERE s.url = v.url
);
