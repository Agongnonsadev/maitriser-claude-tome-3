Trois exemples de cas difficiles, avec le raisonnement :

Déclaration : « URGENT !!! Mon véhicule a été embouti sur le parking du bureau, je suis hors de moi, il me faut une réponse aujourd'hui. »
Raisonnement : un dommage matériel, sur un parking. Le ton et le mot « urgent » ne sont pas des critères, et rien ne bloque la chaussée.
{"branche": "auto", "urgent": false, "motif": "Dommage matériel sans blessé ni véhicule bloqué ; le ton n'est pas un critère."}

Déclaration : « Bonsoir, pas de panique, mais une partie du plafond de la cuisine est tombée et l'eau coule sur le compteur électrique. »
Raisonnement : le ton est calme, mais l'eau sur un compteur électrique est une menace pour la sécurité qui continue.
{"branche": "habitation", "urgent": true, "motif": "Menace pour la sécurité : de l'eau coule sur le compteur électrique."}

Déclaration : « La clinique demande votre accord de prise en charge pour l'accouchement de ma femme, prévu dans trois semaines. »
Raisonnement : une intervention attend un accord, mais dans trois semaines, au-delà de 48 heures.
{"branche": "sante", "urgent": false, "motif": "Intervention prévue au-delà de 48 heures ; demande d'accord à traiter normalement."}
