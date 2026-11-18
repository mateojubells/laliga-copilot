/* Jugadores que suelen nombrarse en las retransmisiones, para que se reconozcan aunque no hayan marcado en 2025/26.
   Escrito a mano: puede estar desactualizado (fichajes, bajas). Edítalo sin miedo: {equipo: [nombres]}.
   El equipo debe coincidir con los nombres de data.js ("FC Barcelona", "Real Madrid", "Atlético de Madrid"...). */
window.ROSTERS = {
 "FC Barcelona": ["Joan García","Szczesny","Koundé","Cubarsí","Araujo","Íñigo Martínez","Balde","Eric García","Gerard Martín","Pedri","Gavi","Frenkie de Jong","Fermín López","Casadó","Marc Bernal","Dani Olmo","Lamine Yamal","Raphinha","Rashford","Ferran Torres","Lewandowski"],
 "Real Madrid": ["Courtois","Lunin","Carvajal","Trent Alexander-Arnold","Militão","Rüdiger","Huijsen","Asencio","Alaba","Carreras","Mendy","Fran García","Tchouaméni","Valverde","Camavinga","Bellingham","Arda Güler","Mastantuono","Brahim","Vinicius Junior","Rodrygo","Mbappé","Endrick","Ceballos"],
 "Atlético de Madrid": ["Oblak","Musso","Molina","Giménez","Le Normand","Lenglet","Hancko","Pubill","Ruggeri","Llorente","Koke","De Paul","Barrios","Gallagher","Baena","Giuliano Simeone","Griezmann","Julián Álvarez","Sørloth","Raspadori","Almada"],
 "Athletic": ["Unai Simón","Yeray","Laporte","Vivian","Paredes","De Marcos","Yuri","Berenguer","Sancet","Iñaki Williams","Nico Williams","Guruzeta","Galarreta","Jauregizar","Rego","Gorosabel","Unai Gómez"],
 "Real Sociedad": ["Remiro","Aramburu","Zubeldia","Aritz Elustondo","Sergio Gómez","Brais Méndez","Zakharyan","Oyarzabal","Kubo","Barrenetxea","Sucic","Turrientes","Becker","Oskarsson"],
 "Villarreal": ["Parejo","Gerard Moreno","Pépé","Comesaña","Pedraza","Foyth","Mikautadze","Ayoze Pérez","Barry","Buchanan","Rafa Marín"],
 "Betis": ["Isco","Lo Celso","Fornals","Antony","Abde","Cucho Hernández","Bartra","Natan","Altimira","Júnior Firpo","Ricardo Rodríguez"],
 "Sevilla": ["Nyland","Badé","Marcao","Gudelj","Sow","Saúl","Lukébakio","Isaac Romero","Alexis Sánchez","Agoumé","Ejuke","Akor Adams","Carmona"],
 "Valencia": ["Dimitrievski","Mosquera","Tárrega","Cömert","Gayà","Pepelu","Javi Guerra","Diego López","Rioja","Ugrinic","Hugo Duro","Sadiq","Lucas Beltrán"],
 "Celta": ["Iago Aspas","Borja Iglesias","Swedberg","Bamba","Marcos Alonso","Starfelt","Hugo Álvarez","Jutglà","Mingueza","Radu"],
 "Osasuna": ["Budimir","Moncayola","Raúl García","Aimar Oroz","Catena","Herrando","Rubén García","Barja","Torró"],
 "Getafe": ["Borja Mayoral","Uche","Milla","Djené","Arambarri","Luis Vázquez","Soria"]
};

/* Cómo suele "oír" el reconocimiento de voz de Chrome a cada jugador (equivocaciones reales y previsibles).
   {nombre del jugador: [variantes]}. Añade las que veas en la caja de transcripción. */
window.ASR_ALIAS = {
 "Lamine Yamal": ["lamin","lamina","la mine","alain","minia","la minia","llamado","lamine jamal","lamin yamal","llamal","yamal","jamal","lamine"],
 "Pedri": ["pedi","pedri","pedry","petri","pedrin"],
 "Gavi": ["gabi","gavi","gaby","gavy"],
 "Cubarsí": ["covarsi","cubarsi","cubarsy","cubars","cuvarsi","cobarsi","cu barsi"],
 "Raphinha": ["rafinha","rafina","rafiña","rafaina","rafinia"],
 "Lewandowski": ["levandowski","lewandovski","levandovski","lewan","lewandoski","levandoski"],
 "Koundé": ["kunde","kounde","cunde","kundé","kondé"],
 "Araujo": ["araujo","arauyo","aragujo","arauho"],
 "Balde": ["balde","balte","balde"],
 "Frenkie de Jong": ["frenkie","frenki","de jong","de yon","dejong","de jon"],
 "Fermín López": ["fermin","fermi","fermin lopez"],
 "Dani Olmo": ["olmo","dani olmo","danielmo"],
 "Íñigo Martínez": ["inigo","inigo martinez"],
 "Ferran Torres": ["ferran","feran","ferrán"],
 "Joan García": ["joan garcia","juan garcia"],
 "Szczesny": ["chesni","cheni","szczesny","checheni","cheseni"],
 "Vinicius Junior": ["vinicius","vinisius","binicius","vini","vinicios","vinisios"],
 "Mbappé": ["mbape","embape","mbappe","mbapé","mbapi","embapé"],
 "Bellingham": ["belingam","bellingam","belinjam","bellinjam","belingan"],
 "Rodrygo": ["rodrigo","rodrygo","rodrigo goes"],
 "Courtois": ["curtua","courtua","kurtua","curtoa","courtois","kurtois"],
 "Valverde": ["valverde","balverde","fede valverde"],
 "Camavinga": ["camavinga","kamavinga","camabinga"],
 "Tchouaméni": ["chuameni","tchuameni","chouameni","chuameny","tchouameni"],
 "Carvajal": ["carvajal","carbajal","carbahal"],
 "Rüdiger": ["rudiger","rudiguer","rudiyer"],
 "Griezmann": ["grizman","griezman","grisman","griesman","griezmann"],
 "Julián Álvarez": ["julian alvarez"],
 "Huijsen": ["huisen","huijsen","juisen","huyisen"],
 "Alexander-Arnold": ["alexander arnold","trent","trent alexander"],
 "Güler": ["guler","arda guler","gueler"],
 "Mastantuono": ["mastantuono","mastantuano","mastantuono"]
};
