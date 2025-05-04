# Pour exécuter ce simulateur, assurez-vous d'avoir installé streamlit :
# pip install streamlit matplotlib

try:
    import streamlit as st
    import matplotlib.pyplot as plt
except ModuleNotFoundError:
    print("Modules nécessaires non installés. Exécutez 'pip install streamlit matplotlib' pour les utiliser.")
    exit()

import requests

def call_urssaf_api(amount: float, type_: str = "BRUTE") -> dict:
    base_situation = {
        "salarié . contrat": "'CDI'",
        #"salarié . contrat . statut cadre": "oui",
        #"salarié . activité partielle": "non"
    }

    if type_ == "NET":
        situation = {**base_situation, "salarié . rémunération . net . à payer avant impôt": f"{amount} €"}
        expressions = [
            "salarié . contrat . salaire brut",
            "salarié . coût total employeur"
        ]
    elif type_ == "TOTAL":
        situation = {**base_situation, "salarié . coût total employeur": f"{amount} €"}
        expressions = [
            "salarié . contrat . salaire brut",
            "salarié . rémunération . net . à payer avant impôt"
        ]
    elif type_ == "BRUTE":
        situation = {**base_situation, "salarié . contrat . salaire brut": f"{amount} €"}
        expressions = [
            "salarié . contrat . salaire brut",
            "salarié . coût total employeur",
            "salarié . rémunération . net . à payer avant impôt"
        ]
    else:
        return {}

    res = requests.post(
        "https://mon-entreprise.urssaf.fr/api/v1/evaluate",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        json={"situation": situation, "expressions": expressions}
    )

    if not res.ok:
        st.error("❌ Erreur appel API URSSAF")
        return {}

    data = res.json().get("evaluate", [])

    # Extract values safely
    salaire_brut = round(data[0].get("nodeValue", 0), 2) if len(data) > 0 else 0
    cout_total = round(data[1].get("nodeValue", 0), 2) if len(data) > 1 else 0
    salaire_net = round(data[2].get("nodeValue", 0), 2) if len(data) > 2 else 0

    return {
        "salaire_brut": salaire_brut,
        "cout_total": cout_total,
        "salaire_net": salaire_net
    }

# === Barème de taux neutre 2025 (reproduit depuis le JS)
TAUX_NEUTRE_2025 = [
    {"seuilMin": 0, "seuilMax": 1619.99, "taux": 0},
    {"seuilMin": 1620, "seuilMax": 1682.99, "taux": 0.5},
    {"seuilMin": 1683, "seuilMax": 1790.99, "taux": 1.3},
    {"seuilMin": 1791, "seuilMax": 1910.99, "taux": 2.1},
    {"seuilMin": 1911, "seuilMax": 2041.99, "taux": 2.9},
    {"seuilMin": 2042, "seuilMax": 2150.99, "taux": 3.5},
    {"seuilMin": 2151, "seuilMax": 2293.99, "taux": 4.1},
    {"seuilMin": 2294, "seuilMax": 2713.99, "taux": 5.3},
    {"seuilMin": 2714, "seuilMax": 3106.99, "taux": 7.5},
    {"seuilMin": 3107, "seuilMax": 3538.99, "taux": 9.9},
    {"seuilMin": 3539, "seuilMax": 3982.99, "taux": 11.9},
    {"seuilMin": 3983, "seuilMax": 4647.99, "taux": 13.8},
    {"seuilMin": 4648, "seuilMax": 5573.99, "taux": 15.8},
    {"seuilMin": 5574, "seuilMax": 6973.99, "taux": 17.9},
    {"seuilMin": 6974, "seuilMax": 8710.99, "taux": 20},
    {"seuilMin": 8711, "seuilMax": 12090.99, "taux": 24},
    {"seuilMin": 12091, "seuilMax": 16375.99, "taux": 28},
    {"seuilMin": 16376, "seuilMax": 25705.99, "taux": 33},
    {"seuilMin": 25706, "seuilMax": 55061.99, "taux": 38},
    {"seuilMin": 55062, "seuilMax": float("inf"), "taux": 43},
]

# === Taux barème URSSAF 2024 simplifié ===
def get_taux_km(cv):
    if cv == 3:
        return 0.529
    elif cv == 4:
        return 0.606
    elif cv == 5:
        return 0.636
    elif cv == 6:
        return 0.665
    else:
        return 0.697

def get_taux_neutre(revenu_mensuel: float) -> float:
    for tranche in TAUX_NEUTRE_2025:
        if tranche["seuilMin"] <= revenu_mensuel <= tranche["seuilMax"]:
            return tranche["taux"]
    return 0.0

def get_euro_to_gbp_rate():
    try:
        url = "https://api.exchangerate.host/live?access_key=05c9d175b525f79a00941a445f33973a&source=EUR&quotes=GBP"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            eur_gbp = data.get("quotes", {}).get("EURGBP")
            if eur_gbp:
                return round(eur_gbp, 4)
            else:
                st.warning("⚠️ Taux EURGBP non trouvé. Utilisation de la valeur par défaut.")
        else:
            st.warning(f"⚠️ Échec de la requête API : {response.status_code}")
    except Exception as e:
        st.warning(f"⚠️ Erreur lors de la récupération du taux EUR -> GBP : {e}")
    return 0.8500  # fallback par défaut
def calcul_are_mensuelle(salaire_brut_total: float, jours_travailles: int) -> float:
    """
    Calcule l'ARE mensuelle à partir du salaire brut total perçu sur la période de référence
    (généralement 18 mois pour un salarié porté) et du nombre total de jours travaillés effectifs.
    """

    if jours_travailles <= 0:
        return 0.0

    # 1. Salaire journalier de référence
    sjr = salaire_brut_total / (jours_travailles * 1.4)

    # 2. Calcul des deux formules
    formule1 = 0.404 * sjr + 12.95
    formule2 = 0.57 * sjr
    are_journaliere = max(formule1, formule2)

    # 3. Plancher et plafond 2024 (à jour)
    are_journaliere = min(are_journaliere, 287.0)  # plafond journalier brut
    are_journaliere = max(are_journaliere, 31.59)  # plancher journalier brut

    # 4. ARE mensuelle sur 30 jours
    return round(are_journaliere * 30, 2)

# Taux de conversion avec possibilité de le modifier manuellement
default_rate = get_euro_to_gbp_rate()
commission_portage = 0.06

# === Titre ===
st.title("💼 Simulateur de Revenu - Portage UK pour Freelance")

# === Entrée utilisateur ===
TJM = st.number_input("TJM (€)", min_value=100, max_value=5000, value=500)
jours_travailles = st.number_input("Jours travaillés / mois", min_value=1, max_value=23, value=20)


# === pré-calcule ===
ca_mensuel = round(TJM * jours_travailles, 2)
commission = round(ca_mensuel * commission_portage, 2)
capital = round(ca_mensuel - commission, 2)
max_salaire = capital * 0.68
# === Entrée utilisateur ===
frais_reels_mensuel = st.number_input("Frais réels mensuels (€)", min_value=0.0, max_value=2000.0, value=200.0)
km_par_mois = st.number_input("Distance domicile-client (km/mois)", min_value=0, max_value=2500, value=100)
cv_fiscaux = st.selectbox("Nombre de chevaux fiscaux", options=[3, 4, 5, 6, 7], index=4)
euro_to_gbp = st.number_input("Taux de conversion EUR -> GBP", value=default_rate, format="%.4f")
# === Infos du simulateur URSSAF ===
salaire_brut = st.number_input("Salaire brut (€)", min_value=2400.0, max_value=max_salaire, value=min(2400.0, max_salaire))
if capital < 2400:
    st.error("⚠️ Le capital est insuffisant pour fixer un salaire brut minimum de 2400 €.")
    st.stop()

# Appel à l’API URSSAF
urssaf_data = call_urssaf_api(salaire_brut, type_="BRUTE")

# Données issues de l'API
cout_employeur = urssaf_data.get("cout_total", 0)
if cout_employeur > capital:
    st.error(f"❌ Le coût employeur calculé ({cout_employeur:.2f} €) dépasse le capital disponible ({capital:.2f} €). Veuillez diminuer le salaire brut pour respecter l'équilibre financier.")
    st.stop()

salaire_net = urssaf_data.get("salaire_net", 0)

# Estimation simplifiée du net après impôt via taux neutre
taux_neutre = get_taux_neutre(salaire_net)
salaire_net_apres_impot = round(salaire_net * (1 - (taux_neutre/100)), 2)

# === Paramètres fixes ===
taux_km = get_taux_km(cv_fiscaux)
NI_class2 = 3.45 * 52

# === Calculs ===
frais_km = round(km_par_mois * taux_km, 2)
frais_total = round(frais_reels_mensuel + frais_km, 2)

cotisation_patronale = round(cout_employeur - salaire_brut, 2)
cotisation_salariale = round(salaire_brut - salaire_net, 2)
impot_source = round(salaire_net - salaire_net_apres_impot, 2)
net_imposable = round(salaire_net + impot_source, 2)
impot_neutre = impot_source

# === Estimation ARE (chômage)
salaire_brut_total = salaire_brut * 18
jours_travailles_total = 220 * 1.5
if salaire_brut_total > 0 and jours_travailles_total > 0:
    are_mensuelle = calcul_are_mensuelle(salaire_brut_total, jours_travailles_total)

benefice_brut_mensuel = round(capital - cout_employeur - frais_total, 2)
benefice_annuel_eur = round(benefice_brut_mensuel * 12, 2)
benefice_annuel_gbp = round(benefice_annuel_eur * euro_to_gbp, 2)

# === IR ===
tax_20 = round(max(0, min(benefice_annuel_gbp, 50270) - 12570) * 0.20, 2)
tax_40 = round(max(0, benefice_annuel_gbp - 50270) * 0.40, 2)
impot_IR = round(tax_20 + tax_40, 2)

# === NI ===
NI_class4_6 = round(max(0, min(benefice_annuel_gbp, 50270) - 12570) * 0.06, 2)
NI_class4_2 = round(max(0, benefice_annuel_gbp - 50270) * 0.02, 2)
total_NI = round(NI_class2 + NI_class4_6 + NI_class4_2, 2)

# === Mensualisation UK (€)
NI_class2_mensuel = round(NI_class2 / 12 / euro_to_gbp, 2)
NI_class4_6_mensuel = round(NI_class4_6 / 12 / euro_to_gbp, 2)
NI_class4_2_mensuel = round(NI_class4_2 / 12 / euro_to_gbp, 2)
impot_IR_20_mensuel = round(tax_20 / 12 / euro_to_gbp, 2)
impot_IR_40_mensuel = round(tax_40 / 12 / euro_to_gbp, 2)

# === Résultats finaux ===
benefice_net_annuel_gbp = round(benefice_annuel_gbp - total_NI - impot_IR, 2)
benefice_net_mensuel_eur = round(benefice_net_annuel_gbp / 12 / euro_to_gbp, 2)
revenu_net_total = round(salaire_net_apres_impot + frais_total + benefice_net_mensuel_eur, 2)

cotisation_uk_mensuelle = round(NI_class2_mensuel + NI_class4_6_mensuel + NI_class4_2_mensuel, 2)
impot_uk_mensuel = round(impot_IR_20_mensuel + impot_IR_40_mensuel, 2)

# === Estimation Retraite ===
# Estimation cotisation retraite
# Retraite de base sur tranche 1
taux_base_salarial = 0.069
taux_base_employeur = 0.0855

# Retraite complémentaire Agirc-Arrco tranche 1
taux_compl_salarial = 0.0787
taux_compl_employeur = 0.1295

# Tranche 1 limitée à 3864€/mois
tranche1 = min(salaire_brut, 3864)

ret_base_salarial = round(tranche1 * taux_base_salarial, 2)
ret_base_employeur = round(tranche1 * taux_base_employeur, 2)

ret_compl_salarial = round(tranche1 * taux_compl_salarial, 2)
ret_compl_employeur = round(tranche1 * taux_compl_employeur, 2)

total_retraite = round(ret_base_salarial + ret_base_employeur + ret_compl_salarial + ret_compl_employeur, 2)

# === Affichage ===

st.success(f"💰 Revenu net mensuel total estimé : {revenu_net_total:.2f} € avec un taux de CA / Net (%) {round((revenu_net_total / ca_mensuel) * 100, 2)} %")

st.subheader("📊 Résumé mensuel détaillé")
st.write({
    "CA mensuel (€)": f"{ca_mensuel} €",
    "Commission portage 6% (€)": f"{commission} €",
    "Capital (€)": f"{capital} €",
    "Salaire brut (€)": f"{salaire_brut} €",
    "Coût de salaire (€)": f"{cout_employeur} €",
    "Cotisation patronale (€)": f"{cotisation_patronale} €",
    "Cotisation salariale (€)": f"{cotisation_salariale} €",
    "Taux neutre (%)": f"{taux_neutre} %",
    "Impot prélevé à la source (€)": f"{impot_source} €",
    "Net imposable (€)": f"{net_imposable} €",
    "Salaire net d'impôt (€)": f"{salaire_net} €",
    "ARE mensuelle estimée": f"{are_mensuelle:.2f} €",
    "Frais kilométriques (€)": f"{frais_km} €",
    "Frais réels (€)": f"{frais_reels_mensuel} €",
    "Total des frais réels (€)": f"{frais_total} €",
    "Bénéfice UK brut mensuel (€)": f"{benefice_brut_mensuel} €",
    "Bénéfice net mensuel (€)": f"{benefice_net_mensuel_eur} €",
    "Total revenu net encaissé (€)": f"{revenu_net_total} €",
    "Taux CA / Net (%)": f"{round((revenu_net_total / ca_mensuel) * 100, 2)} %"
})

st.subheader("📘 Détails mensuels UK")
st.write({
    "Cotisation UK Class 2 (€)": f"{NI_class2_mensuel} €",
    "Cotisation UK Class 4 - 6% (€)": f"{NI_class4_6_mensuel} €",
    "Cotisation UK Class 4 - 2% (€)": f"{NI_class4_2_mensuel} €",
    "Total cotisations UK (€)": f"{cotisation_uk_mensuelle} €",
    "Impôt UK - 20% (€)": f"{impot_IR_20_mensuel} €",
    "Impôt UK - 40% (€)": f"{impot_IR_40_mensuel} €",
    "Total impôt UK (€)": f"{impot_uk_mensuel} €",
    "Bénéfice net UK mensuel (€)": f"{benefice_net_mensuel_eur} €"
})

st.subheader("🧓 Estimation Cotisation Retraite (mensuelle)")
st.write({
    "Retraite de base (salarié)": f"{ret_base_salarial} €",
    "Retraite de base (employeur)": f"{ret_base_employeur} €",
    "Complémentaire Agirc-Arrco (salarié)": f"{ret_compl_salarial} €",
    "Complémentaire Agirc-Arrco (employeur)": f"{ret_compl_employeur} €",
    "Total cotisations retraite": f"{total_retraite} €"
})

# === Graphe camembert CA ===
st.subheader("📊 Répartition du Chiffre d'affaires")
fig1, ax1 = plt.subplots()
ax1.pie(
    [commission, revenu_net_total, cotisation_patronale + cotisation_salariale + impot_neutre, cotisation_uk_mensuelle + impot_uk_mensuel],
    labels=[
        f"Commission ({round(commission)}€)",
        f"Revenu Net Total ({round(revenu_net_total)}€)",
        f"Cotisations FR ({round(cotisation_patronale + cotisation_salariale + impot_neutre)}€)",
        f"Cotisations + Impôts UK ({round(cotisation_uk_mensuelle + impot_uk_mensuel)}€)"
    ],
    autopct='%1.1f%%'
)
ax1.axis('equal')
st.pyplot(fig1)

# === Graphe salaire FR ===
st.subheader("📊 Répartition du Coût de Salaire")
fig2, ax2 = plt.subplots()
ax2.pie(
    [cotisation_patronale, cotisation_salariale, impot_source, salaire_net],
    labels=[
        f"Cotisation Patronale ({round(cotisation_patronale)}€)",
        f"Cotisation Salariale ({round(cotisation_salariale)}€)",
        f"Impôt à la source ({round(impot_source)}€)",
        f"Salaire Net ({round(salaire_net)}€)"
    ],
    autopct='%1.1f%%'
)
ax2.axis('equal')
st.pyplot(fig2)


# === Graphe Bénéfice UK ===
st.subheader("📊 Répartition du Bénéfice UK (Mensuel)")
fig3, ax3 = plt.subplots()
ax3.pie(
    [cotisation_uk_mensuelle, impot_uk_mensuel, benefice_net_mensuel_eur],
    labels=[
        f"Cotisations UK ({round(cotisation_uk_mensuelle)}€)",
        f"Impôts UK ({round(impot_uk_mensuel)}€)",
        f"Bénéfice Net UK ({round(benefice_net_mensuel_eur)}€)"
    ],
    autopct='%1.1f%%'
)
ax3.axis('equal')
st.pyplot(fig3)
