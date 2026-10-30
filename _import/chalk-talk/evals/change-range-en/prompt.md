---
name: change-range-en
tags: [change, en]
max_turns: 30
timeout_seconds: 600
allowed_tools: [Skill, Read, Write, Edit, Bash]
---
This is my lesson (lesson.json):

```json
{"id": "juros-fatura", "title": "Juros compostos ↔ a fatura", "category": "Matemática", "width": 900, "height": 560, "background": "grid", "params": {"taxa": {"label": "juros do rotativo (% ao mês)", "min": 1, "max": 15, "step": 1, "value": 12}}, "vars": {"r": "taxa / 100", "bx": 90, "by": 130, "bw": 720, "bh": 340, "ymax": 6000, "final": "1000 * (1 + r)^12", "simples": "1000 * (1 + r*12)", "ex": "bx + bw", "ey": "by + bh - min(final, ymax) / ymax * bh"}, "steps": [{"type": "text", "at": [40, 72], "text": "por que a dívida do rotativo dispara?", "size": 42, "say": "Você deixou R$ 1.000 no rotativo do cartão. O que acontece em um ano?"}, {"type": "polyline", "points": [["bx", "by - 10"], ["bx", "by + bh"], ["bx + bw + 10", "by + bh"]], "style": {"width": 2.4}}, {"type": "text", "at": ["bx + bw", "by + bh + 38"], "text": "meses →", "anchor": "end", "size": 26, "style": {"color": "#5E5A52"}}, {"type": "text", "at": ["bx - 10", "by - 18"], "text": "R$", "anchor": "middle", "size": 26, "style": {"color": "#5E5A52"}}, {"type": "plot", "fn": "1000 * (1 + r*x)", "domain": [0, 12], "range": [0, "ymax"], "box": {"x": "bx", "y": "by", "w": "bw", "h": "bh"}, "style": {"color": "#8C8578", "width": 2.4, "dashed": true}, "say": "Se os juros fossem simples, a dívida subiria em linha reta."}, {"type": "text", "at": ["ex - 8", "min(by + bh - min(simples, ymax)/ymax*bh + 62, by + bh - 8)"], "text": "simples: R$ {simples:0}", "anchor": "end", "size": 26, "style": {"color": "#5E5A52"}}, {"type": "pause", "ms": 400}, {"type": "plot", "fn": "1000 * (1 + r)^x", "domain": [0, 12], "range": [0, "ymax"], "box": {"x": "bx", "y": "by", "w": "bw", "h": "bh"}, "style": {"color": "#C8442C", "width": 3.4}, "say": "Mas no rotativo o juro cobra juro do juro. A curva entorta para cima."}, {"type": "arrow", "from": ["ex - 230", "ey - 48"], "to": ["ex - 10", "ey - 6"], "style": {"width": 2.4}}, {"type": "text", "at": ["ex - 240", "ey - 56"], "text": "12 meses: R$ {final:0}", "anchor": "end", "size": 36, "style": {"color": "#C8442C"}, "say": "Em doze meses, os mil reais viram isso. Mexa na taxa e veja a curva mudar."}]}
```

Save it as lesson.json, let the rate go up to 20 and build it again.
