# Calage des apports — note de synthèse

## Conclusion

Le calage est **partiellement conforme** : 3 section(s) sur 4 atteignent la cible en volume, en débit de pointe et en forme. Les sections non validées sont listées ci-dessous et doivent être reprises avant exploitation des résultats.

- Débit de pointe : de 95.1 % à 100.2 % de la cible
- Volume : de 95.1 % à 100.2 % de la cible
- Décalage temporel maximal : 0.40 h (surveillé, non corrigé)

## Détail par section

- **Section 1 (amont)** — OK — pointe 100.2 % | volume 100.2 % | forme 100.0 % | decalage +0.40 h
- **Section 2** — OK — pointe  99.5 % | volume  99.5 % | forme 100.0 % | decalage +0.40 h
- **Section 3** — OK — pointe  98.2 % | volume  98.2 % | forme 100.0 % | decalage +0.40 h
- **Section 4 (aval)** — NON VALIDÉ — pointe  95.1 % | volume  95.1 % | forme 100.0 % | decalage +0.40 h

## Vérifications exigées par le guide méthodologique

Conformément à Lang & Lavabre (2007), p. 81, les points suivants ont été contrôlés :

1. Cohérence de forme entre l'hydrogramme de référence et le calcul, évaluée après recalage temporel.
2. Cohérence fréquentielle, par comparaison du volume et du débit de pointe à la cible HSMF.
3. Absence de dérive en fréquence vers l'aval, contrôlée par le profil longitudinal des débits de pointe.

## Outils

Le pilotage de HEC-RAS s'appuie sur **ras-commander v0.99.1** (CLB Engineering Corporation), bibliothèque libre — github.com/gpt-cmdr/ras-commander. Merci de conserver cette mention dans toute publication reprenant ces résultats (rascommander.info/ras/cite/).