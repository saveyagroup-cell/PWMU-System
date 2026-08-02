// ===========================================================================
// Simple i18n — data-i18n attributes get swapped based on selected language.
// Language choice persists in localStorage (this is a real downloaded project
// file running in the user's own browser, not a Claude artifact preview).
// ===========================================================================
const I18N = {
  en: {
    "header.title": "Ecobyte — PWMU Intelligence Center",
    "header.govt": "Government of Chhattisgarh",
    "header.badge1": "Digital India Initiative",
    "header.badge2": "Swachh Bharat Mission",
    "header.online": "System Online",
    "header.language": "Language",

    "nav.home": "Home",
    "nav.gate": "Gate & Security",
    "nav.segregation": "AI Segregation",
    "nav.dashboard": "Dashboard",

    "hub.heading": "Executive Command Hub",
    "hub.subheading": "Select a module to open its dedicated live view",
    "hub.usp.title": "Project Highlights",

    "hub.card.vehicle.title": "Vehicle Entry/Exit Counter",
    "hub.card.vehicle.desc": "Directional line-crossing IN/OUT counter for gate traffic.",
    "hub.card.plate.title": "ANPR — Number Plate Records",
    "hub.card.plate.desc": "Plate detection, OCR reading, and a searchable database log.",
    "hub.card.waste_primary.title": "Primary Waste Segregation",
    "hub.card.waste_primary.desc": "Metal vs. General/Other waste classification.",
    "hub.card.waste_secondary.title": "Secondary Plastic Classification",
    "hub.card.waste_secondary.desc": "Fine-grained sorting into 7 resin (RIC) types.",
    "hub.card.thief.title": "PWMU Shed Security",
    "hub.card.thief.desc": "24/7 theft and unattended-material anomaly detection.",
    "hub.card.analytics.title": "Analytics & Audit Reports",
    "hub.card.analytics.desc": "Graphs, trends, and full digital audit trail export.",

    "common.open": "Open Module",
    "common.live": "LIVE",
    "common.idle": "IDLE",
    "common.back": "← Back to Hub",
  },
  hi: {
    "header.title": "इकोबाइट — पीडब्ल्यूएमयू इंटेलिजेंस सेंटर",
    "header.govt": "छत्तीसगढ़ सरकार",
    "header.badge1": "डिजिटल इंडिया पहल",
    "header.badge2": "स्वच्छ भारत मिशन",
    "header.online": "सिस्टम ऑनलाइन",
    "header.language": "भाषा",

    "nav.home": "होम",
    "nav.gate": "गेट और सुरक्षा",
    "nav.segregation": "एआई पृथक्करण",
    "nav.dashboard": "डैशबोर्ड",

    "hub.heading": "कार्यकारी कमांड हब",
    "hub.subheading": "किसी भी मॉड्यूल का लाइव व्यू खोलने के लिए चुनें",
    "hub.usp.title": "परियोजना की विशेषताएं",

    "hub.card.vehicle.title": "वाहन प्रवेश/निकास काउंटर",
    "hub.card.vehicle.desc": "गेट ट्रैफ़िक के लिए दिशात्मक इन/आउट काउंटर।",
    "hub.card.plate.title": "एएनपीआर — नंबर प्लेट रिकॉर्ड",
    "hub.card.plate.desc": "प्लेट पहचान, ओसीआर रीडिंग, और खोजने योग्य डेटाबेस लॉग।",
    "hub.card.waste_primary.title": "प्राथमिक अपशिष्ट पृथक्करण",
    "hub.card.waste_primary.desc": "धातु बनाम सामान्य/अन्य अपशिष्ट वर्गीकरण।",
    "hub.card.waste_secondary.title": "द्वितीयक प्लास्टिक वर्गीकरण",
    "hub.card.waste_secondary.desc": "7 रेज़िन (आरआईसी) प्रकारों में बारीक छँटाई।",
    "hub.card.thief.title": "पीडब्ल्यूएमयू शेड सुरक्षा",
    "hub.card.thief.desc": "24/7 चोरी और असंगत सामग्री विसंगति पहचान।",
    "hub.card.analytics.title": "विश्लेषण और ऑडिट रिपोर्ट",
    "hub.card.analytics.desc": "ग्राफ़, रुझान, और पूर्ण डिजिटल ऑडिट ट्रेल निर्यात।",

    "common.open": "मॉड्यूल खोलें",
    "common.live": "लाइव",
    "common.idle": "निष्क्रिय",
    "common.back": "← हब पर वापस जाएं",
  },
  cg: {
    "header.title": "इकोबाइट — पीडब्ल्यूएमयू इंटेलिजेंस सेंटर",
    "header.govt": "छत्तीसगढ़ शासन",
    "header.badge1": "डिजिटल इंडिया पहल",
    "header.badge2": "स्वच्छ भारत मिशन",
    "header.online": "सिस्टम चालू हे",
    "header.language": "भाषा",

    "nav.home": "होम",
    "nav.gate": "गेट अउ सुरक्षा",
    "nav.segregation": "एआई छंटाई",
    "nav.dashboard": "डैशबोर्ड",

    "hub.heading": "कमांड हब",
    "hub.subheading": "कोनो भी मॉड्यूल के लाइव व्यू देखे बर ओला चुनव",
    "hub.usp.title": "परियोजना के खासियत",

    "hub.card.vehicle.title": "गाड़ी आवाजाही गिनती",
    "hub.card.vehicle.desc": "गेट म गाड़ी के अंदर-बाहर होय के गिनती।",
    "hub.card.plate.title": "नंबर प्लेट रिकार्ड",
    "hub.card.plate.desc": "प्लेट पहिचान, ओसीआर पढ़ई, अउ रिकार्ड के लॉग।",
    "hub.card.waste_primary.title": "पहिली कचरा छंटाई",
    "hub.card.waste_primary.desc": "धातु अउ आने कचरा के अलगाव।",
    "hub.card.waste_secondary.title": "दूसर प्लास्टिक छंटाई",
    "hub.card.waste_secondary.desc": "7 किसम के प्लास्टिक म बारीक छंटाई।",
    "hub.card.thief.title": "पीडब्ल्यूएमयू सेड सुरक्षा",
    "hub.card.thief.desc": "24/7 चोरी अउ गड़बड़ी के पहिचान।",
    "hub.card.analytics.title": "विश्लेषण अउ रिपोर्ट",
    "hub.card.analytics.desc": "ग्राफ, रुझान, अउ पूरा रिपोर्ट डाउनलोड।",

    "common.open": "मॉड्यूल खोलव",
    "common.live": "लाइव",
    "common.idle": "बंद",
    "common.back": "← हब कोति वापिस",
  },
};

function applyTranslations(lang) {
  const dict = I18N[lang] || I18N.en;
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.getAttribute("data-i18n");
    if (dict[key]) el.textContent = dict[key];
  });
}

function initI18n() {
  const saved = localStorage.getItem("pwmu_lang") || "en";
  const switcher = document.getElementById("lang-switcher");
  if (switcher) {
    switcher.value = saved;
    switcher.addEventListener("change", () => {
      localStorage.setItem("pwmu_lang", switcher.value);
      applyTranslations(switcher.value);
    });
  }
  applyTranslations(saved);
}

document.addEventListener("DOMContentLoaded", initI18n);
