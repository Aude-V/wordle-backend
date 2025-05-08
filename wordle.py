from uuid import uuid4
from fastapi import Cookie, FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from random import randint
import unicodedata

app=FastAPI()

app.add_middleware(CORSMiddleware,allow_origins=["*","http://localhost:8000"],allow_credentials=True)


# Fonction pour enlever les accents
def enlever_accents(texte):
    return ''.join(
        c for c in unicodedata.normalize('NFD', texte)
        if unicodedata.category(c) != 'Mn'
    )
# Lecture du fichier et transformation des mots
with open('french.txt', 'r', encoding='utf-8') as f:
    mots = [enlever_accents(ligne.strip()).upper() for ligne in f if ligne.strip()] #liste des mots autorisés, en majuscule et sans accents


#Fonction auxiliaire pour plus loin
def trouver_indice(mot,lettre):
    for i in range(len(mot)):
        if mot[i]==lettre:
            return i
    return None


nb_essais_max=6

class Grille:
    nb_essais:int
    essais_utilisateurs=dict[str,int]
    taille_mot:int
    mot_solution:str
    keys:set[str]
    users:set[str]
    finis:dict[str,bool] #va contenir les id des utilisateurs ayant fini cette partie
    historique:dict[str, list[str]] #va contenir l'historique des propositions de chaque utilisateur
    def __init__(self,nb_essais:int=nb_essais_max,mot:str=None):
        if mot==None:
            mot=mots[randint(0,len(mots)-1)]
        self.nb_essais=nb_essais
        self.taille_mot=len(mot)
        self.mot_solution=mot
        self.keys=set()
        self.users=set()
        self.essais_utilisateurs={}
        self.finis={}
        self.historique={}
    def create_new_key(self):
        key = str(uuid4()) #uuid4 crée une clef universellement unique
        self.keys.add(key)
        return key
    def is_valid_key(self,key:str):
        return key in self.keys
    def create_new_user_id(self):
        user_id=str(uuid4())
        self.users.add(user_id)
        self.finis[user_id]=False
        self.historique[user_id] = []
        return user_id
    def is_valid_user_id(self,user_id:str):
        return user_id in self.users
    
grilles:dict[str,Grille]={} #contient les différentes grilles créées
    
@app.get("/api/v1/wordle/preinit")
async def preinit():
    grille = Grille()
    key = grille.create_new_key()
    grilles[key] = grille
    res = JSONResponse({"key": key})
    res.set_cookie("key", key, httponly=True, samesite="none", secure=True, max_age=3600)
    return res

@app.get("/api/v1/wordle/init")
async def init(query_key:str=Query(alias="key"),
               cookie_key:str=Cookie(alias="key")):
    if query_key not in grilles:
        return {"error": "la grille n'existe pas"}
    grille=grilles[query_key]
    if query_key!=cookie_key:
        return{"error":"les clefs ne correspondent pas"}
    if not grille.is_valid_key(cookie_key):
        return{"error":"la clef n'est pas valide"}
    
    user_id=grille.create_new_user_id()

    res=JSONResponse ({
        "id":user_id,
        "taille_mot":grille.taille_mot,
        "nb_essais":grille.nb_essais #on ne met pas mot_solution dans res pour ne pas spoiler le jeu au joueur
    })

    res.set_cookie("id",user_id,secure=True,samesite="none",max_age=3600)
    return res

@app.get("/api/v1/wordle/proposition")
async def proposition(mot_propose:str,
                 query_user_id:str=Query(alias="id"),
                 cookie_key:str=Cookie(alias="key"),
                 cookie_user_id:str=Cookie(alias='id')):
    if cookie_key not in grilles:
        return {"error": "la grille n'existe pas"}
    grille=grilles[cookie_key]
    if query_user_id!=cookie_user_id:
        return{"error":"les clefs ne correspondent pas"}
    if not grille.is_valid_key(cookie_key):
        return{"error":"la clef n'est pas valide"}
    if not grille.is_valid_user_id(cookie_user_id):
        return{"error":"la clef n'est pas valide"}
    
    mot_solution=grille.mot_solution
    mot_propose=mot_propose.upper() #car tous les mots solution sont en lettres majuscules
    #on incrémente l'essai de l'utilisateur
    if query_user_id not in grille.essais_utilisateurs:
        grille.essais_utilisateurs[query_user_id] = 1
    else:
        grille.essais_utilisateurs[query_user_id]+=1
    essai=grille.essais_utilisateurs[query_user_id]

    if grille.finis.get(query_user_id, False):
        return {"error":"la partie est terminée"}
    if essai>nb_essais_max:
        return {"error":"tu as dépassé le nombre maximal d'essais"}
    if mot_propose not in mots:
        return {"error":"le mot n'existe pas"}
    if len(mot_propose)!=grille.taille_mot:
        return{"error":"le mot n'est pas de la bonne longueur"}
    
    grille.historique[query_user_id].append(mot_propose)

    if mot_propose==mot_solution:
        grille.finis[query_user_id] = True #on marque la partie comme terminée
        return {"success":[1]*grille.taille_mot}
    if essai==nb_essais_max: #si c'était le dernier essai
        grille.finis[query_user_id] = True
        return {"fail":-1,"mot solution":mot_solution} #on révèle le mot solution car le joueur a perdu
    
    result=[]
    lettres_solution=list(mot_solution)
    lettres_proposees=list(mot_propose)
    for indice in range(len(mot_propose)):
        if mot_propose[indice]==mot_solution[indice]: #la lettre est la bonne
            result.append(1)
            lettres_solution[indice]=None
            lettres_proposees[indice]=None
        else:
            result.append(None)
    #ici, result contient autant d'éléments que de lettres dans le mot, avec 1 si la lettre est bien et au bon endroit, None sinon
    for indice in range(len(mot_propose)): #on reparcourt le mot pour détecter les lettres qui sont au mauvais endroit
        if result[indice]==None:
            if lettres_proposees[indice]!=None and lettres_proposees[indice] in lettres_solution: #la lettre est à la mauvaise place
                result[indice]=0
                lettres_solution[trouver_indice(lettres_solution,lettres_proposees[indice])]=None
            else:
                result[indice]=-1 #la lettre n'est pas dans le mot ou est déjà bien placée autre part

    return JSONResponse({"id":query_user_id,
                         "result_proposition":result,
                         "historique": grille.historique[query_user_id]}) #pour pouvoir afficher l'historique des propositions