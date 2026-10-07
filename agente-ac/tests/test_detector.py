from datetime import datetime, timezone

from worker.detector import entradas_recientes

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns="http://www.w3.org/2005/Atom">
 <entry><yt:videoId>nuevo000001</yt:videoId><title>Entrevista de hoy</title>
  <published>2026-10-07T12:00:00+00:00</published></entry>
 <entry><yt:videoId>viejo000001</yt:videoId><title>Entrevista antigua</title>
  <published>2026-09-01T12:00:00+00:00</published></entry>
</feed>"""


def test_solo_entradas_de_las_ultimas_48_horas():
    ahora = datetime(2026, 10, 7, 20, 0, tzinfo=timezone.utc)
    assert entradas_recientes(FEED, ahora) == [{"youtube_id": "nuevo000001", "titulo": "Entrevista de hoy"}]
