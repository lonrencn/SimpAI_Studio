import hashlib
import json
import csv
import functools
import os
import re
from difflib import SequenceMatcher

import modules.canvas_danbooru_policy as canvas_danbooru_policy
import modules.canvas_danbooru_service as canvas_danbooru_service


DETAIL_SCENE_PATTERNS = (
    r"\u8be6\u7ec6.*(?:\u573a\u666f|\u60c5\u666f|\u80cc\u666f)",
    r"(?:\u573a\u666f|\u60c5\u666f|\u80cc\u666f).*(?:\u8be6\u7ec6|\u4e30\u5bcc)",
    r"\u4e30\u5bcc(?:\u753b\u9762|\u573a\u666f|\u80cc\u666f)",
    r"\u573a\u666f\u7167|\u573a\u666f\u56fe|\u60c5\u666f\u56fe",
    r"\u6545\u4e8b\u611f|\u53d9\u4e8b|\u6c1b\u56f4|\u73af\u5883\u4e92\u52a8",
    r"\u4e0d\u8981\u53ea\u6709.*\u89d2\u8272|\u53ea\u6709.*\u89d2\u8272",
    r"\bdetailed(?:\s+(?:scene|background|setting))?\b",
    r"\brich(?:\s+(?:scene|background|setting))?\b",
    r"\bnarrative\s+(?:scene|illustration)\b",
)


PLAIN_SCENE_PATTERNS = (
    r"\u7b80\u5355\u80cc\u666f|\u7b80\u6d01\u80cc\u666f|\u7eaf\u8272\u80cc\u666f|\u767d\u5e95",
    r"\u900f\u660e\u80cc\u666f|\u80cc\u666f.{0,6}\u900f\u660e|\u900f\u660e\u5e95|\u900f\u660e\u5e95\u8272|\u65e0\u80cc\u666f|\u53bb\u80cc\u666f|\u62a0\u56fe|\u6263\u56fe",
    r"\u5934\u50cf|\bavatar\b|\bicon\b|\bprofile\s+picture\b",
    r"\u8d34\u7eb8|\bsticker\b",
    r"\u89d2\u8272\u8bbe\u5b9a\u56fe|\u8bbe\u5b9a\u56fe|\u7acb\u7ed8|\bcharacter\s+sheet\b|\breference\s+sheet\b|\bmodel\s+sheet\b",
    r"\bsimple\s+background\b|\btransparent\s+background\b|\bno\s+background\b|\bwhite\s+background\b",
)


COMBAT_SCENE_PATTERNS = (
    r"\u6218\u6597|\u6253\u6597|\u5bf9\u6218|\u4ea4\u6218|\u6218\u573a|\u6218\u6597\u573a\u666f|\u52a8\u6001|\u52a8\u4f5c",
    r"\u6218\u8d25|\u6230\u6557|\u8d25\u5317|\u6557\u5317|\u843d\u8d25|\u843d\u6557|\u8d25\u9000|\u6557\u9000",
    r"\u88ab[^，。,.!?]{0,8}(?:\u6253|\u63cd|\u653b\u51fb|\u653b\u64ca|\u6bb4\u6253|\u6253\u4f24|\u6253\u50b7|\u638c\u63b4|\u62f3\u51fb)",
    r"\bbattle(?:field)?\b|\bfight(?:ing)?\b|\bcombat\b|\baction\s+scene\b|\bdynamic\b",
    r"\b(?:being\s+)?(?:hit|beaten|attacked|punched|slapped)\b",
)


DEFEATED_CORE_PATTERNS = (
    r"\u6218\u8d25|\u6230\u6557|\u8d25\u5317|\u6557\u5317|\u843d\u8d25|\u843d\u6557|\u8d25\u9000|\u6557\u9000",
    r"\bdefeat(?:ed)?\b|\blos(?:t|ing)\s+(?:a\s+)?battle\b|\bafter\s+(?:a\s+)?defeat\b",
)


DEFEATED_DOWN_PATTERNS = (
    r"\u88ab.{0,8}(?:\u51fb\u5012|\u64ca\u5012|\u6253\u5012|\u6253\u8d25|\u6253\u6557)|\u5012\u5730|\u8db4\u5730|\u8eba\u5730",
    r"\bknock(?:ed)?\s+down\b|\bfall(?:en)?\s+(?:down|over)\b|\bcollapsed?\b|\bon\s+the\s+ground\b",
)


DEFEATED_SCENE_PATTERNS = (
    *DEFEATED_CORE_PATTERNS,
    *DEFEATED_DOWN_PATTERNS,
)


KNEELING_INTENT_PATTERNS = (
    r"\u8dea|\u8dea\u5730|\u8dea\u4e0b|\u5355\u819d|\u55ae\u819d",
    r"\bkneel(?:ing)?\b|\bon\s+one\s+knee\b",
)


BATTLE_DAMAGED_CLOTHING_PATTERNS = (
    r"\u6218\u635f|\u6230\u640d|\u7834\u8863|\u7834\u70c2\u8863\u670d|\u8863\u670d.{0,6}(?:\u7834\u788e|\u7834\u635f|\u7834\u88c2|\u6495\u88c2)|\u7834\u7532",
    r"\btorn\s+clothes?\b|\bripped\s+clothes?\b|\btattered(?:\s+clothes?|\s+armor|\s+armour)?\b|\bbattle[-_\s]?damaged\b",
)


PASSIVE_EXTERNAL_ACTOR_PATTERNS = (
    r"\u88ab(?:\u4eba|\u7537\u4eba|\u5973\u4eba|\u7537\u6027|\u5973\u6027|\u7537\u5b69|\u5973\u5b69|\u654c\u4eba|\u5bf9\u624b|[^，。,.!?]{0,6})(?:\u6253|\u63cd|\u653b\u51fb|\u653b\u64ca|\u6bb4\u6253|\u6253\u4f24|\u6253\u50b7|\u638c\u63b4|\u62f3\u51fb|\u6293\u4f4f|\u63a7\u5236|\u538b\u5236|\u6346\u7ed1|\u7d81\u4f4f|\u62b1\u4f4f|\u62b1\u5728\u6000\u91cc)",
    r"\b(?:being\s+)?(?:hit|beaten|attacked|punched|slapped|grabbed|restrained|controlled|held)\b",
    r"(?<![a-z0-9])full[_\s-]?nelson(?![a-z0-9])",
)


PASSIVE_ATTACK_INTENT_PATTERNS = (
    r"\u88ab[^，。,.!?]{0,8}(?:\u6253|\u63cd|\u653b\u51fb|\u653b\u64ca|\u6bb4\u6253|\u6253\u4f24|\u6253\u50b7|\u638c\u63b4|\u62f3\u51fb)",
    r"\b(?:being\s+)?(?:hit|beaten|attacked|punched|slapped)\b",
)


TRAVEL_SCENE_PATTERNS = (
    r"\u65c5\u6e38|\u65c5\u884c|\u51fa\u6e38|\u89c2\u5149|\u884c\u674e|\u8f66\u7ad9|\u673a\u573a|\u5730\u56fe",
    r"\btravel(?:ing)?\b|\btour(?:ist|ism)?\b|\bsightseeing\b|\bstation\b|\bairport\b|\bsuitcase\b|\bbackpack\b|\bcamera\b|\bmap\b",
)


SELFIE_SCENE_PATTERNS = (
    r"\u81ea\u62cd|\u624b\u673a|\u624b\u6a5f|\u667a\u80fd\u624b\u673a|\u667a\u80fd\u624b\u6a5f|\bselfie\b|\bself[-_\s]?shot\b|\bsmartphone\b|\bcellphone\b|\bphone\b",
)


LEISURE_SCENE_PATTERNS = (
    r"\u4f11\u95f2|\u653e\u677e|\u5496\u5561|\u58c1\u7089|\u793c\u7269|\u79ae\u7269|\u793c\u76d2|\u79ae\u76d2|\u8336\u9986|\u8336\u5ba4|\u91ce\u9910|\u901b\u8857|\u8d2d\u7269|\u65e5\u5e38|\u88ab\u5582|\u6295\u5582|\u5582\u98df|\u5403\u996d|\u5403\u4e1c\u897f",
    r"\bleisure\b|\brelax(?:ing)?\b|\bcafe\b|\bcoffee\b|\bmug\b|\bfireplace\b|\bgift(?:\s+box)?\b|\bpresent\b|\btea\s*house\b|\bpicnic\b|\bshopping\b|\bdaily\b|\bfeed(?:ing)?\b|\beat(?:ing)?\b",
)


SLEEP_SCENE_PATTERNS = (
    r"\u7761|\u7761\u89c9|\u719f\u7761|\u5e8a\u4e0a|\u5367\u5ba4|\u5bdd\u5ba4",
    r"\bsleep(?:ing)?\b|\basleep\b|\bon\s+bed\b|\bbed(?:room)?\b",
)


BATHING_SCENE_PATTERNS = (
    r"\u6d17\u6fa1|\u6d74\u5ba4|\u6c90\u6d74|\u6ce1\u6fa1|\u6dcb\u6d74",
    r"\bbath(?:room|ing)?\b|\bshower(?:ing)?\b|\bbathtub\b|\bonsen\b",
)


POOL_SCENE_PATTERNS = (
    r"\u6cf3\u6c60|\u6e38\u6cf3\u6c60|\u6c34\u6c60",
    r"\bswimming\s+pool\b|\bpool(?:side)?\b",
)


BEACH_SCENE_PATTERNS = (
    r"\u6d77\u8fb9|\u6d77\u6ee9|\u6c99\u6ee9|\u6cf3\u88c5|\u6cf3\u8863|\u73a9\u6c34",
    r"\bbeach\b|\bseaside\b|\bocean\b|\bswimsuits?\b|\bbikini\b",
)


KISS_SCENE_PATTERNS = (
    r"\u4eb2\u5634|\u63a5\u543b|\u4eb2\u543b|\u4eb2(?:\u4e00\u4e0b|\u4e00\u53e3|\u4eb2)|\u543b",
    r"\bkiss(?:ing)?\b|\bmake\s*out\b",
)


ROMANCE_SCENE_PATTERNS = (
    r"\u4e24\u6027\u4e92\u52a8|\u60c5\u4fa3|\u7ea6\u4f1a|\u604b\u7231|\u7275\u624b|\u66a7\u6627|\u7537\u5973\u4e92\u52a8|\u5a5a\u7eb1|\u5a5a\u7d17|\u65b0\u5a18",
    r"\bromance\b|\bromantic\b|\bcouple\b|\bdate\b|\bdating\b|\bholding\s+hands\b|\bwedding\s+dress\b|\bbridal\b",
)


GROUP_OTHER_PEOPLE_PATTERNS = (
    r"小朋友们|孩子们|儿童们|幼儿们|同学们|朋友们|大家",
    r"一群(?:小朋友|孩子|儿童|幼儿|同学|朋友|人)",
    r"(?:和|跟|与|陪).{0,14}(?:小朋友|孩子|儿童|幼儿|同学|朋友).{0,8}(?:一起)?",
    r"\bwith\s+(?:children|kids|classmates|friends|students|a\s+group\s+of\s+people)\b",
    r"\b(?:children|kids|classmates|friends|students)\s+(?:together|around|playing|play)\b",
)


GROUP_PLAY_SCENE_PATTERNS = (
    r"(?:和|跟|与|陪).{0,14}(?:小朋友|孩子|儿童|幼儿|同学|朋友).{0,10}(?:一起)?玩",
    r"(?:小朋友们|孩子们|儿童们|幼儿们|同学们|朋友们).{0,12}玩",
    r"\bplay(?:ing)?\s+with\s+(?:children|kids|classmates|friends|students)\b",
)


KINDERGARTEN_SCENE_PATTERNS = (
    r"幼儿园|托儿所|学前班",
    r"\bkindergarten\b|\bpreschool\b|\bnursery\s+school\b",
)


OUTDOOR_SCENE_PATTERNS = (
    r"\u6237\u5916|\u5916\u666f|\u81ea\u7136|\u516c\u56ed|\u82b1\u56ed|\u68ee\u6797|\u6d77\u8fb9|\u6d77\u6ee9|\u8349\u5730|\u8857\u5934",
    r"\boutdoor(?:s)?\b|\bnature\b|\bpark\b|\bgarden\b|\bforest\b|\bbeach\b|\bseaside\b|\bmeadow\b|\bstreet\b",
)


PURE_SCENERY_PATTERNS = (
    r"(?:\u80cc\u666f|\u98ce\u666f|\u573a\u666f|\u58c1\u7eb8).*(?:\u4e0d\u8981|\u4e0d\u5e26|\u522b\u753b|\u6ca1\u6709|\u65e0)(?:\u4eba|\u4eba\u7269|\u89d2\u8272)",
    r"(?:\u4e0d\u8981|\u4e0d\u5e26|\u522b\u753b|\u6ca1\u6709|\u65e0)(?:\u4eba|\u4eba\u7269|\u89d2\u8272).*(?:\u80cc\u666f|\u98ce\u666f|\u573a\u666f|\u58c1\u7eb8)",
    r"(?:\u6ca1\u6709|\u65e0|\u4e0d\u8981|\u4e0d\u5e26|\u522b\u753b|no|without).{0,8}(?:\u4eba|\u4eba\u7269|\u89d2\u8272|humans?|people|characters?).*(?:\u57ce\u5e02|\u8857\u9053|\u8857|\u6e56|\u5c71|\u6d77|\u82b1\u56ed|garden|city|street|lake|mountain|ocean|landscape|scenery)",
    r"(?:\u57ce\u5e02|\u8857\u9053|\u8857|\u6e56|\u5c71|\u6d77|\u82b1\u56ed|garden|city|street|lake|mountain|ocean|landscape|scenery).*(?:\u6ca1\u6709|\u65e0|\u4e0d\u8981|\u4e0d\u5e26|\u522b\u753b|no|without).{0,8}(?:\u4eba|\u4eba\u7269|\u89d2\u8272|humans?|people|characters?)",
    r"\u7eaf(?:\u80cc\u666f|\u98ce\u666f)|\u7a7a\u955c|\u65e0\u4eba(?:\u98ce\u666f|\u573a\u666f)",
    r"(?:background|scenery|landscape|wallpaper).*(?:no\s*humans?|no\s*people|without\s*(?:people|characters?))",
    r"(?:no\s*humans?|no\s*people|without\s*(?:people|characters?)).*(?:background|scenery|landscape|wallpaper)",
    r"\b(?:wide\s+)?landscape\b|\bscenery\b|\bsunset\s+over\s+(?:the\s+)?ocean\b",
)


PURE_SCENERY_EXCLUDE_PATTERNS = (
    r"\u4e0d\u8981\u53ea\u6709.*(?:\u4eba\u7269|\u89d2\u8272)|\u4e0d\u60f3\u53ea\u6709.*(?:\u4eba\u7269|\u89d2\u8272)",
    r"\u9700\u8981.*(?:\u573a\u666f|\u80cc\u666f).*(?:\u4eba\u7269|\u89d2\u8272)",
)


COMPOSITION_RULES = (
    (r"\u534a\u8eab|\u534a\u8eab\u7167|\u4e0a\u534a\u8eab|\bbust\b|\bupper[-_\s]?body\b", ("upper_body",)),
    (r"\u5168\u8eab|\bfull[-_\s]?body\b", ("full_body",)),
    (r"\u7acb\u7ed8|\bstanding\s+illustration\b", ("full_body", "standing", "looking_at_viewer")),
    (r"\u8096\u50cf|\u5934\u50cf|\bportrait\b", ("portrait",)),
    (r"\u8fd1\u666f|\u7279\u5199|\bclose[-_\s]?up\b", ("close-up",)),
    (r"\u4fa7\u8138|\u4fa7\u9762|\bside\s*profile\b|\bprofile\s+portrait\b", ("profile", "from_side", "looking_to_the_side")),
    (r"\u56de\u5934|\u8f6c\u5934|\u8f49\u982d|\blooking\s+back\b|\bturning\s+head\b", ("looking_back", "looking_at_viewer")),
    (r"\u770b\u7740\u955c\u5934|\u6b63\u9762|\blooking at viewer\b|\bfacing viewer\b", ("looking_at_viewer",)),
    (r"\u5fae\u7b11|\u7b11|\bsmile\b", ("smile",)),
    (r"\u4e25\u8083|\u8ba4\u771f|\bserious\b", ("serious",)),
    (r"\u5750|\bsitting\b|\bsit\b", ("sitting",)),
    (r"\u7ad9|\bstanding\b|\bstand\b", ("standing",)),
    (r"\u8d70|\u884c\u8d70|\bwalking\b|\bwalk\b", ("walking",)),
    (r"\u8dd1|\u5954\u8dd1|\brunning\b|\brun\b", ("running",)),
    (r"\u8df3|\u8df3\u8dc3|\bjump(?:ing)?\b", ("jumping",)),
)


PLAIN_SCENE_RULES = (
    (r"\u7b80\u5355\u80cc\u666f|\u7b80\u6d01\u80cc\u666f|\bsimple\s+background\b", ("simple_background",)),
    (r"\u900f\u660e\u80cc\u666f|\u80cc\u666f.{0,6}\u900f\u660e|\u900f\u660e\u5e95|\u900f\u660e\u5e95\u8272|\u65e0\u80cc\u666f|\u53bb\u80cc\u666f|\u62a0\u56fe|\u6263\u56fe|\btransparent\s+background\b|\bno\s+background\b", ("transparent_background", "full_body", "standing")),
    (r"\u767d\u5e95|\bwhite\s+background\b", ("white_background",)),
    (r"\u89d2\u8272\u8bbe\u5b9a\u56fe|\u8bbe\u5b9a\u56fe|\bcharacter\s+sheet\b|\breference\s+sheet\b|\bmodel\s+sheet\b", ("reference_sheet", "simple_background")),
)

PLAIN_SCENE_CARRY_RULES = (
    (r"\u6bd4\u8036|(?<![a-z0-9_])v[-_\s]?sign(?![a-z0-9_])|(?<![a-z0-9_])peace\s+sign(?![a-z0-9_])", ("v_sign", "peace_sign")),
    (r"\u7c89\u4e1d|\u7537\u7c89|(?<![a-z0-9_])fans?(?![a-z0-9_])", ("fan",)),
    (r"\u5076\u50cf|(?<![a-z0-9_])idol(?![a-z0-9_])", ("idol",)),
    (r"\u5fae\u7b11|\u7b11|(?<![a-z0-9_])smile(?![a-z0-9_])", ("smile",)),
)


PLAIN_OUTPUT_TAGS = {
    "simple_background",
    "transparent_background",
    "white_background",
    "reference_sheet",
    "character_sheet",
}

CHARACTER_SUBJECT_COUNT_HINTS = {
    "ganyu_(genshin_impact)": "1girl",
    "nahida_(genshin_impact)": "1girl",
    "klee_(genshin_impact)": "1girl",
    "klee_(blossoming_starlight)_(genshin_impact)": "1girl",
    "lisa_(genshin_impact)": "1girl",
    "hu_tao_(genshin_impact)": "1girl",
    "xianyun_(genshin_impact)": "1girl",
    "raiden_shogun": "1girl",
    "matou_sakura": "1girl",
    "tohsaka_rin": "1girl",
    "ayanami_rei": "1girl",
    "misaka_mikoto": "1girl",
    "saber_(fate)": "1girl",
    "saber_alter": "1girl",
    "artoria_pendragon_(fate)": "1girl",
    "hatsune_miku": "1girl",
    "venti_(genshin_impact)": "1boy",
    "zhongli_(genshin_impact)": "1boy",
    "wanderer_(genshin_impact)": "1boy",
    "scaramouche_(genshin_impact)": "1boy",
    "phainon_(honkai:_star_rail)": "1boy",
    "morichika_rinnosuke": "1boy",
    "mario": "1boy",
    "frieren_(sousou_no_frieren)": "1girl",
    "fern_(sousou_no_frieren)": "1girl",
    "stark_(sousou_no_frieren)": "1boy",
    "makima": "1girl",
    "gotou_hitori": "1girl",
    "ijichi_nijika": "1girl",
    "yamada_ryou": "1girl",
    "kita_ikuya": "1girl",
    "hoshino_ai": "1girl",
    "sakura_miko": "1girl",
    "hoshimachi_suisei": "1girl",
    "amiya_(arknights)": "1girl",
    "kal'tsit_(arknights)": "1girl",
    "texas_(arknights)": "1girl",
    "lappland_(arknights)": "1girl",
    "sorasaki_hina": "1girl",
    "irisviel_(fate)": "1girl",
    "eula_(genshin_impact)": "1girl",
}


SCENE_RULES = (
    (r"\u6559\u5ba4|\bclassroom\b", ("indoors", "classroom", "window", "desk")),
    (r"幼儿园|托儿所|学前班|\bkindergarten\b|\bpreschool\b|\bnursery\s+school\b", ("indoors", "kindergarten", "classroom", "school")),
    (r"\u6821\u56ed|\bcampus\b", ("outdoors", "school", "campus", "walking", "sky", "day")),
    (r"\u5b66\u6821|\bschool\b", ("school", "classroom", "indoors")),
    (r"\u7a97|\bwindow\b", ("window", "curtains")),
    (r"\u684c|\u4e66\u684c|\bdesk\b|\btable\b", ("desk", "table")),
    (r"\u4e66|\u770b\u4e66|\u9605\u8bfb|\u8bfb\u4e66|\bbook\b|\bread", ("book", "holding_book", "reading", "sitting")),
    (r"\u8336\u9986|\u8336\u5ba4|\btea\s*house\b|\bteahouse\b", ("indoors", "table", "window", "tea", "teacup", "holding_cup", "sitting", "casual")),
    (r"\u5496\u5561\u5385|\u5496\u5561\u9986|\u5496\u5561\u5e97|\bcafe\b|\bcoffee\s*shop\b", ("indoors", "cafe", "table", "window", "cup", "coffee", "sitting", "casual")),
    (r"\u5496\u5561|\bcoffee\b", ("coffee", "cup", "drinking", "sitting", "casual")),
    (r"\u58c1\u7089|\bfireplace\b", ("indoors", "fireplace", "fire", "couch")),
    (r"\u624b\u673a|\u624b\u6a5f|\u667a\u80fd\u624b\u673a|\u667a\u80fd\u624b\u6a5f|\bsmartphone\b|\bcellphone\b|\bphone\b", ("phone", "holding_phone")),
    (r"\u793c\u7269|\u79ae\u7269|\u793c\u76d2|\u79ae\u76d2|\bgift(?:\s+box)?\b|\bpresent\b", ("gift", "gift_box")),
    (r"\u5a5a\u7eb1|\u5a5a\u7d17|\u65b0\u5a18|\bwedding\s+dress\b|\bbridal\b", ("wedding_dress", "bridal_veil", "bouquet")),
    (r"\u804a\u5929|\btalk(?:ing)?\b", ("talking", "smile")),
    (r"\u4e0b\u5348|\bafternoon\b", ("afternoon", "warm_atmosphere")),
    (r"\u559d\u8336|\u559d|\u8336|\u8336\u676f|\btea\b|\bteacup\b", ("tea", "teacup", "holding_cup", "drinking")),
    (r"\u5367\u5ba4|\u5bdd\u5ba4|\bbedroom\b", ("indoors", "bedroom", "bed", "on_bed", "pillow")),
    (r"\u5e8a\u4e0a|\u5e8a|\bon\s+bed\b|\bbed\b", ("indoors", "bedroom", "bed", "on_bed", "pillow", "blanket")),
    (r"\u719f\u7761|\u7761\u89c9|\u7761|\bsleep(?:ing)?\b|\basleep\b", ("sleeping", "lying", "closed_eyes")),
    (r"\u6a31\u82b1|\u82b1\u74e3|\bcherry\b|\bsakura\s+blossoms?\b|\bpetals?\b", ("outdoors", "sakura", "cherry_blossoms", "petals", "falling_petals", "tree")),
    (r"\u82b1\u56ed|\bgarden\b", ("outdoors", "garden", "flower", "path")),
    (r"\u516c\u56ed|\bpark\b", ("outdoors", "park", "bench", "walking")),
    (r"\u68ee\u6797|\u6811\u6797|\bforest\b", ("outdoors", "forest", "plant", "sunlight")),
    (r"\u5929\u7a7a|\bsky\b", ("outdoors", "sky")),
    (r"\u4e91|\u4e91\u6d77|\bclouds?\b", ("outdoors", "sky", "cloud", "clouds")),
    (r"\u5c71|\u5c71\u95f4|\u5c71\u9876|\bmountain\b", ("outdoors", "mountain", "sky")),
    (r"\u8349\u5730|\u8349\u576a|\bgrass\b|\bmeadow\b", ("outdoors", "grass")),
    (r"\u529e\u516c\u5ba4|\boffice\b", ("indoors", "office", "desk", "paper")),
    (r"\u5904\u7406\u6587\u4ef6|\u5199|\u7b14|\u6587\u4ef6|\u7eb8\u5f20|\bdocument\b|\bpaper|\bwriting\b|\bpen\b", ("paper", "papers", "writing", "holding_pen")),
    (r"\u821e\u53f0|\bconcert\b|\bstage\b", ("stage", "microphone", "spotlight", "audience")),
    (r"\u5531|\u6f14\u5531|\bsing", ("singing", "microphone", "performing", "audience")),
    (r"\u56fe\u4e66\u9986|\blibrary\b", ("indoors", "library", "bookshelf", "book")),
    (r"\u795e\u793e|\u9e1f\u5c45|\bshrine\b|\btorii\b", ("outdoors", "shrine", "torii")),
    (r"\u6d77\u8fb9|\u6d77\u6ee9|\u6c99\u6ee9|\bbeach\b|\bseaside\b", ("outdoors", "beach", "ocean", "sand", "sky", "cloud", "clouds", "day", "sunlight", "blurry_background")),
    (r"\u6d77|\u6d77\u6d0b|\bocean\b|\bsea\b", ("outdoors", "ocean", "water", "wave", "horizon", "sky", "cloud", "clouds")),
    (r"\u5ba4\u5185.{0,6}(?:\u6cf3\u6c60|\u6e38\u6cf3\u6c60)|(?:\u6cf3\u6c60|\u6e38\u6cf3\u6c60).{0,6}\u5ba4\u5185|\bindoor\s+pool\b|\bindoor\s+swimming\s+pool\b", ("indoors", "pool", "water")),
    (r"\u6cf3\u6c60|\u6e38\u6cf3\u6c60|\bswimming\s+pool\b|\bpoolside\b|\bpool\b", ("pool", "water", "poolside")),
    (r"\u6cf3\u88c5|\u6cf3\u8863|\u6bd4\u57fa\u5c3c|\bswimsuits?\b|\bbikini\b", ("swimsuit",)),
    (r"\u6551\u751f\u5708|\u6e38\u6cf3\u5708|\u6cf3\u5708|\blifebuoy\b|\blife\s+preserver\b|\bswim\s+ring\b|\binnertube\b", ("lifebuoy",)),
    (r"(?:\u62ff\u7740|\u62b1\u7740|\u624b\u6301).{0,8}(?:\u6551\u751f\u5708|\u6e38\u6cf3\u5708|\u6cf3\u5708)|(?:holding|carrying).{0,12}(?:lifebuoy|life\s+preserver|swim\s+ring|innertube)", ("lifebuoy", "holding_swim_ring", "holding")),
    (r"一起玩|陪.{0,8}玩|玩耍|嬉戏|玩水|\bplay(?:ing)?\b|\bplaying around\b", ("playing",)),
    (r"\u81ea\u62cd|\bselfie\b|\bself[-_\s]?shot\b", ("selfie", "holding_phone", "portrait", "looking_at_viewer")),
    (r"\u65c5\u6e38|\u65c5\u884c|\u51fa\u6e38|\u89c2\u5149|\btravel(?:ing)?\b|\btour(?:ist|ism)?\b|\bsightseeing\b", ("outdoors", "city", "street", "backpack", "camera", "walking")),
    (r"\u8f66\u7ad9|\btrain\s*station\b", ("train_station", "suitcase", "walking")),
    (r"\u673a\u573a|\bairport\b", ("airport", "suitcase", "walking")),
    (r"\u8fb9\u8d70\u8fb9\u62cd|\u62cd\u6444|(?<!\u81ea)\u62cd\u7167|\u65c5\u884c\u7167|\u76f8\u673a|\bcamera\b|\bphoto", ("camera", "holding_camera")),
    (r"\u5730\u56fe|\bmap\b", ("map", "holding")),
    (r"\u4f11\u95f2|\u65e5\u5e38|\u653e\u677e|\bleisure\b|\bdaily\b|\brelax", ("casual", "sitting", "soft_lighting")),
    (r"\u91ce\u9910|\bpicnic\b", ("outdoors", "picnic", "food", "sitting")),
    (r"\u901b\u8857|\u8d2d\u7269|\bshopping\b", ("city", "street", "shopping", "shop", "walking")),
    (r"\u4eb2\u5634|\u63a5\u543b|\u4eb2\u543b|\u4eb2(?:\u4e00\u4e0b|\u4e00\u53e3|\u4eb2)|\u543b|\bkiss(?:ing)?\b|\bmake\s*out\b", ("kiss", "couple", "facing_another", "closed_eyes", "close-up", "soft_lighting")),
    (r"\u4e24\u6027\u4e92\u52a8|\u60c5\u4fa3|\u7ea6\u4f1a|\u604b\u7231|\u7275\u624b|\u624b\u7275\u624b|\u7275\u7740.{0,6}\u624b|\u62c9\u7740.{0,6}\u624b|\bromance\b|\bcouple\b|\bdate\b|\bdating\b|\bholding\s+hands\b", ("couple", "holding_hands", "looking_at_another", "walking")),
    (r"\u96ea|\u96ea\u666f|\u96ea\u5730|\bsnow\b|\bsnowy\b", ("snow", "winter", "outdoors")),
    (r"\u623f\u95f4|\u5ba4\u5185|\u5c4b\u5185|\bindoor", ("indoors", "window", "table")),
    (r"\u73bb\u7483|\u534a\u900f\u660e|\bglass\b|\btranslucent\b", ("glass", "translucent")),
    (r"\u6d17\u6fa1|\u6ce1\u6fa1|\u6c90\u6d74|\u5165\u6d74|\bbath(?:ing)?\b", ("indoors", "bathroom", "bathing", "wet", "bathtub")),
    (r"\u6dcb\u6d74|\u51b2\u6fa1|\bshower(?:ing)?\b", ("indoors", "bathroom", "showering", "shower_head", "wet")),
    (r"\u57ce\u5e02|\u5e02\u533a|\u8857|\u8857\u9053|\bcity\b|\bstreet\b|urban", ("outdoors", "city", "street")),
    (r"\u767d\u5929|\u65e5\u95f4|\u6674\u5929|\bday(?:time)?\b|\bdaylight\b", ("day", "sunlight")),
    (r"\u4e0b\u96e8|\u96e8\u5929|\u96e8\u591c|\brain", ("rain", "street", "puddle", "wet", "umbrella", "holding_umbrella")),
    (r"\u591c|\u591c\u665a|\bnight\b", ("night", "moonlight")),
    (r"\u9ec4\u660f|\u508d\u665a|\u65e5\u843d|\bsunset\b|\bevening\b", ("sunset", "evening", "backlighting")),
    (r"\u9633\u5149|\u5149\u7ebf|\bsunlight\b|\blight rays?\b", ("sunlight", "light_rays")),
    (r"\u602a\u7269|\u654c\u4eba|\u9b54\u7269|\bmonster\b|\bcreature\b|\benemy\b", ("monster", "creature")),
    (r"\u8054\u624b.{0,8}\u6218\u6597|\u534f\u529b.{0,8}\u6218\u6597|\bteam(?:ed)?\s+up\b.*\b(?:battle|fight|combat)\b|\b(?:battle|fight|combat)\b.*\btogether\b", ("monster", "creature")),
    (r"\u88ab[^，。,.!?]{0,8}(?:\u6253|\u63cd|\u653b\u51fb|\u653b\u64ca|\u6bb4\u6253|\u6253\u4f24|\u6253\u50b7|\u62f3\u51fb)|\b(?:being\s+)?(?:hit|beaten|attacked|punched)\b", ("facing_another", "fighting", "hitting", "injury")),
    (r"\u88ab[^，。,.!?]{0,8}(?:\u638c\u63b4)|\b(?:being\s+)?slapped\b", ("facing_another", "slapping", "injury")),
    (r"(?<![a-z0-9])full[_\s-]?nelson(?![a-z0-9])", ("full_nelson", "restrained", "facing_another")),
    (r"\u6218\u8d25|\u6230\u6557|\u8d25\u5317|\u6557\u5317|\u843d\u8d25|\u843d\u6557|\u8d25\u9000|\u6557\u9000|\bdefeat(?:ed)?\b|\blos(?:t|ing)\s+(?:a\s+)?battle\b", ("kneeling", "on_ground", "injury")),
    (r"\u88ab.{0,8}(?:\u51fb\u5012|\u64ca\u5012|\u6253\u5012|\u6253\u8d25|\u6253\u6557)|\u5012\u5730|\u8db4\u5730|\u8eba\u5730|\bknock(?:ed)?\s+down\b|\bfall(?:en)?\s+(?:down|over)\b|\bcollapsed?\b", ("lying", "on_ground", "injury")),
    (r"\u8dea|\u8dea\u5730|\u8dea\u4e0b|\u5355\u819d|\u55ae\u819d|\bkneel(?:ing)?\b|\bon\s+one\s+knee\b", ("kneeling", "on_ground")),
    (r"\u7ffb\u767d\u773c|\u767d\u773c|\broll(?:ed|ing)?\s+eyes?\b", ("rolling_eyes", "white_eyes", "empty_eyes")),
    (r"\u8863\u670d.{0,6}(?:\u7834\u788e|\u7834\u635f|\u7834\u88c2|\u6495\u88c2)|\u6218\u635f|\u6230\u640d|\u7834\u8863|\u7834\u70c2\u8863\u670d|\u7834\u7532|\btorn\s+clothes?\b|\bripped\s+clothes?\b|\btattered(?:\s+clothes?|\s+armor|\s+armour)?\b|\bbattle[-_\s]?damaged\b", ("torn_clothes",)),
    (r"\u6218\u6597|\u6253\u6597|\u5bf9\u6218|\u4ea4\u6218|\u6218\u573a|\u52a8\u6001|\u52a8\u4f5c|\bbattle(?:field)?\b|\bfight(?:ing)?\b|\bcombat\b|\bdynamic\b", ("outdoors", "battlefield", "battle", "fighting", "smoke", "debris", "dynamic_pose", "motion_blur", "cinematic_lighting")),
    (r"\u62ff\u5251|\u5251|\bsword\b", ("sword", "holding_sword")),
    (r"\u62ff\u82b1|\u624b\u6367\u82b1|\bholding\s+flower\b", ("holding_flower", "flower")),
    (r"\u4f38\u624b|\u4f38\u5411\u955c\u5934|\breaching\b", ("reaching_towards_viewer", "outstretched_hand")),
    (r"\u98de|\u6f02\u6d6e|\u60ac\u6d6e|\bfloating\b", ("floating", "wind")),
    (r"\u6e56|\u6e56\u9762|\blake\b", ("outdoors", "lake", "water", "reflection", "tree", "forest", "sky")),
    (r"\u96fe|\u96fe\u6c14|\u8584\u96fe|\bfog\b|\bmist\b", ("fog", "mist", "soft_lighting")),
    (r"\u5012\u5f71|\u53cd\u5c04|\breflection\b", ("reflection", "water")),
    (r"\u65e9\u6668|\u6e05\u6668|\bmorning\b", ("morning", "soft_lighting")),
    (r"\u6392\u7403|\bvolleyball\b", ("volleyball", "sports", "playing", "sand")),
    (r"\u5251\u9053|\bkendo\b|\bdojo\b|\bshinai\b", ("indoors", "dojo", "kendo", "shinai", "wooden_sword", "hakama", "kendogi", "martial_arts", "sparring")),
    (r"\u4e50\u961f|\u4e50\u5668|\u6392\u7ec3|\u6f14\u594f|\u5f39|\bband\b|\brehearsal\b|\bguitar\b|\bdrums?\b", ("indoors", "stage", "concert", "music_room", "rehearsal", "guitar", "bass_guitar", "drums", "playing", "microphone", "audience", "standing", "spotlight", "stage_lighting")),
    (r"\u8d5b\u535a\u670b\u514b|\u672a\u6765\u57ce\u5e02|(?<![a-z0-9_])cyberpunk(?![a-z0-9_])|(?<![a-z0-9_])futuristic(?![a-z0-9_])|(?<![a-z0-9_])neon(?![a-z0-9_])", ("cyberpunk", "futuristic", "neon_lights")),
    (r"\u5ba2\u5385|\u6c99\u53d1|\u7535\u89c6|\u7535\u5b50\u6e38\u620f|\u6253\u6e38\u620f|\u73a9\u6e38\u620f|\u6e38\u620f\u673a|\u6e38\u620f\u624b\u67c4|\bliving\s*room\b|\bcouch\b|\bvideo\s*games?\b|\bgame\s*controller\b", ("indoors", "living_room", "couch", "television", "video_games", "game_controller", "holding_controller", "sitting")),
    (r"\u62c9\u9762\u5e97|\bramen\s+shop\b", ("indoors", "restaurant", "table")),
    (r"\u62c9\u9762|\bramen\b", ("indoors", "sitting", "ramen", "bowl", "chopsticks", "eating")),
    (r"\u900f\u660e\u80cc\u666f|\u80cc\u666f.{0,6}\u900f\u660e|\u900f\u660e\u5e95|\u900f\u660e\u5e95\u8272|\u65e0\u80cc\u666f|\u53bb\u80cc\u666f|\u62a0\u56fe|\u6263\u56fe|\btransparent\s+background\b|\bno\s+background\b", ("transparent_background", "full_body", "standing")),
    (r"\u6bd4\u8036|\bv[-_\s]?sign\b|\bpeace\s+sign\b", ("v_sign", "peace_sign")),
    (r"\u7c89\u4e1d|\u7537\u7c89|\bfans?\b", ("fan",)),
    (r"\u8d70\u5eca|\u8fc7\u9053|\bhallway\b|\bcorridor\b", ("indoors", "hallway", "corridor")),
    (r"\u535a\u58eb|\bdoctor\b", ("doctor", "male")),
    (r"\u8138\u7ea2|\u5bb3\u7f9e|\bblush\b", ("blush",)),
    (r"\u5427\u53f0|\u9152\u5427|\u9152\u5427|\bbar\b|\bcounter\b|\balcohol\b", ("indoors", "bar", "counter", "alcohol")),
    (r"\u559d\u9152|\b(?:drinking|holding)\s+(?:alcohol|beer|wine|cocktail|liquor|whiskey|sake)\b|\b(?:alcohol|beer|wine|cocktail|liquor|whiskey|sake)\b", ("drinking", "holding_glass", "alcohol")),
    (r"(?<![a-z0-9_])drinking(?![a-z0-9_])", ("drinking", "holding_cup")),
    (r"\u8c22\u5e55|\bbow(?:ing)?\b", ("bowing", "audience", "stage")),
)


GENERIC_PROMPT_RULES = (
    (r"\u9b54\u6cd5\u5c11\u5973|\u9b54\u6cd5\u5973\u5b69|\bmagical\s+girl\b", ("1girl", "magical_girl")),
    (r"\u4fa6\u63a2|\bdetective\b", ("detective",)),
    (r"\u8def\u706f|\blamppost\b", ("lamppost",)),
    (r"\u62c9\u9762|\bramen\b", ("ramen", "bowl", "chopsticks", "eating", "holding_chopsticks")),
    (r"\u53cc\u9a6c\u5c3e|\btwintails?\b", ("twintails",)),
    (r"\u9ed1\u53d1|\u9ed1\u9aee|\u9ed1\u8272\u5934\u53d1|\u9ed1\u8272\u982d\u9aee|\u9ed1\u8272.{0,4}\u53cc\u9a6c\u5c3e|\bblack\s+hair\b", ("black_hair",)),
    (r"jk\s*\u5236\u670d|\bjk\b|\u6c34\u624b\u670d|\u6821\u670d|\bserafuku\b|\bschool\s*uniform\b", ("serafuku", "school_uniform")),
    (r"\u7ea2\u53d1|\u7ea2\u5934\u53d1|\bred\s+hair\b", ("red_hair",)),
    (r"\u897f\u88c5|\bsuit\b", ("suit", "formal", "professional")),
    (r"\u505a\u996d|\u505a\u83dc|\u70f9\u996a|\bcook(?:ing)?\b", ("apron", "frying_pan", "stove", "steam", "cooking")),
    (r"\u4fa7\u8138|\u4fa7\u9762|\bside\s*profile\b|\bprofile\s+portrait\b", ("profile", "from_side", "looking_to_the_side")),
    (r"\u6bd4\u8036|\bv[-_\s]?sign\b|\bpeace\s+sign\b", ("v_sign", "peace_sign")),
    (r"\u5076\u50cf|\u7c89\u4e1d|\u7537\u7c89|\u8868\u6f14|\bidol\b|\bfans?\b|\bperform(?:ing)?\b", ("idol", "performing", "audience", "stage_lighting")),
    (r"\u5b66\u751f|\u6821\u56ed|\bcampus\b|\bstudent\b", ("student", "school_uniform", "campus")),
    (r"\u533b\u751f|\bdoctor\b", ("doctor",)),
    (r"\u8d70\u5eca|\u8fc7\u9053|\bhallway\b|\bcorridor\b", ("indoors", "hallway", "corridor")),
    (r"\u8138\u7ea2|\u5bb3\u7f9e|\bblush\b", ("blush",)),
    (r"\u5427\u53f0|\u9152\u5427|\u9152|\bbar\b|\bcounter\b|\balcohol\b", ("bar", "counter", "alcohol", "holding_glass")),
    (r"\u73bb\u7483|\u900f\u660e|\bglass\b|\btranslucent\b", ("glass", "translucent")),
)


SEMANTIC_SCENE_RULES = (
    (r"(?:和|跟|与|陪).{0,14}(?:小朋友|孩子|儿童|幼儿|同学|朋友).{0,10}(?:一起)?玩|\bplay(?:ing)?\s+with\s+(?:children|kids|classmates|friends|students)\b", ("playing", "looking_at_another")),
    (r"\u62e5\u62b1|\u62b1\u5728\u4e00\u8d77|\u76f8\u62e5|\u4ece\u80cc\u540e\u62b1|\bhug(?:ging)?\b|\bembrac(?:e|ing)\b", ("hug", "cuddling", "facing_another")),
    (r"\u4f9d\u504e|\u4f9d\u5077|\u4f9d\u5728.*\u8eab\u8fb9|\u9760\u5728.*\u80a9|\u4eb2\u5bc6|\bcuddl(?:e|ing)\b|\bsnuggl(?:e|ing)\b", ("cuddling", "facing_another")),
    (r"\u7275\u624b|\u624b\u7275\u624b|\u7275\u7740.{0,6}\u624b|\u62c9\u7740.{0,6}\u624b|\bholding\s+hands\b", ("holding_hands", "couple", "walking", "looking_at_another")),
    (r"\u6328\u5728\u4e00\u8d77|\u9760\u5f97\u5f88\u8fd1|\u8d34\u8d34|\bclose\s+together\b", ("facing_another",)),
    (r"\u6084\u6084\u8bdd|\u8033\u8bed|\u4f4e\u58f0|\u5728.*\u8033\u8fb9|\bwhisper(?:ing)?\b", ("whispering", "close-up", "facing_another")),
    (r"\u6478\u5934|\u6478.*\u5934|\u624b\u653e\u5728.*\u5934|\bpat(?:ting)?\s+(?:head|another)\b", ("hand_on_another's_head", "facing_another")),
    (r"\u6478\u8138|\u6367\u8138|\u6478.*\u8138\u988a|\u6258.*\u4e0b\u5df4|\bhand\s+on\s+(?:another'?s\s+)?cheek\b", ("hand_on_another's_cheek", "facing_another", "close-up")),
    (r"\u58c1\u549a|\bkabedon\b|\bagainst\s+wall\b", ("kabedon", "against_wall", "facing_another", "close-up")),
    (r"(?<![a-z0-9])full[_\s-]?nelson(?![a-z0-9])", ("full_nelson", "restrained", "facing_another")),
    (r"\u516c\u4e3b\u62b1|\bprincess\s+carry\b|\bbridal\s+carry\b", ("princess_carry", "couple", "facing_another")),
    (r"\u80cc\u7740|\u80cc\u8d77|\u80cc\u4e0a|\bpiggyback\b", ("piggyback", "couple", "smile")),
    (r"\u819d\u6795|\u6795\u5728.*\u817f|\blap\s+pillow\b|\bhead\s+(?:in|on)\s+lap\b", ("lap_pillow", "lying", "indoors", "bedroom")),
    (r"\u79c1\u5bc6|\u66a7\u6627|\u4eb2\u5bc6\u884c\u4e3a|\u4eb2\u5bc6|\u4e8c\u4eba\u72ec\u5904|\bintimate\b|\bprivate\b", ("indoors", "bedroom", "bed", "on_bed", "couple", "cuddling")),
    (r"\u5171\u6491.*\u4f1e|\u4e00\u8d77\u6491\u4f1e|\u540c\u6491.*\u4f1e|\u540c\u4e00\u628a\u4f1e|\u76f8\u5408\u4f1e|\bshared\s+(?:an?\s+|the\s+)?umbrella\b|\bsharing\s+(?:an?\s+|the\s+)?umbrella\b", ("shared_umbrella", "umbrella", "rain", "couple", "walking")),
    (r"\u96e8\u4e2d|\u6dcb\u96e8|\brainy\b|\bin\s+the\s+rain\b", ("rain", "wet", "puddle", "umbrella")),
    (r"\u505a\u996d|\u505a\u83dc|\u70f9\u996a|\u4e00\u8d77\u505a\u996d|\bcook(?:ing)?\b", ("indoors", "kitchen", "cooking", "food")),
    (r"\u88ab\u5582|\u6295\u5582|\u5582\u98df|\bfeed(?:ing)?\b", ("food", "eating", "feeding", "open_mouth")),
    (r"\u5403\u996d|\u5403\u4e1c\u897f|\u5206\u4eab\u98df\u7269|\beat(?:ing)?\b|\bsharing\s+food\b", ("food", "eating", "sharing_food")),
    (r"\u8df3\u821e|\u5171\u821e|\u821e\u4f1a|\bdanc(?:e|ing)\b", ("dancing", "couple", "stage", "spotlight")),
    (r"\u54ed|\u54ed\u6ce3|\u843d\u6cea|\u773c\u6cea|\bcry(?:ing)?\b|\btears?\b", ("crying", "tears", "close-up")),
    (r"\u53d7\u4f24|\u4f24\u75d5|\u6d41\u8840|\u6218\u635f|\binjur(?:y|ed)\b|\bwound(?:ed)?\b", ("injury", "blood", "serious")),
    (r"\u8ffd\u9010|\u8ffd\u8d76|\u9003\u8dd1|\u5954\u8dd1|\bchas(?:e|ing)\b", ("running", "motion_blur", "dynamic_pose", "street")),
    (r"\u5bf9\u5cd9|\u5bf9\u8d28|\u5251\u62d4\u5f29\u5f20|\bstandoff\b|\bface[-_\s]?off\b", ("facing_another", "serious", "battle", "dynamic_pose")),
    (r"\u4e00\u8d77\u770b\u4e66|\u5171\u8bfb|\bread(?:ing)?\s+together\b", ("book", "reading", "holding_book", "couple", "sitting")),
    (r"\u7948\u7977|\u7977\u544a|\bpray(?:ing)?\b", ("praying", "own_hands_together")),
)


# Character identities are resolved separately; scene enrichment must come from
# the request/history intent instead of per-character defaults.
INTENT_SCENE_PROFILES = {
    "combat": (
        "outdoors", "battlefield", "battle", "fighting", "smoke", "debris",
        "dynamic_pose", "motion_blur", "cinematic_lighting",
        "depth_of_field", "blurry_background",
    ),
    "travel": (
        "outdoors", "city", "street", "backpack", "camera",
        "holding_camera", "walking", "looking_back", "sunlight",
        "depth_of_field", "blurry_background",
    ),
    "pool": (
        "indoors", "pool", "water", "swimsuit", "poolside",
        "soft_lighting", "depth_of_field", "blurry_background",
    ),
    "selfie": (
        "selfie", "holding_phone", "portrait", "looking_at_viewer",
        "soft_lighting", "depth_of_field", "blurry_background",
    ),
    "leisure": (
        "indoors", "cafe", "window", "table", "food", "holding_cup",
        "drinking", "sitting", "casual", "sunlight", "depth_of_field",
        "blurry_background",
    ),
    "group_play": (
        "indoors", "kindergarten", "classroom", "school", "playing",
        "looking_at_another", "standing", "day", "soft_lighting",
        "depth_of_field", "blurry_background",
    ),
    "romance": (
        "outdoors", "park", "bench", "couple", "holding_hands",
        "looking_at_another", "walking", "sunset", "backlighting",
        "depth_of_field", "blurry_background",
    ),
    "kiss": (
        "indoors", "window", "curtains", "couple", "kiss",
        "facing_another", "closed_eyes", "close-up", "soft_lighting",
        "depth_of_field", "blurry_background",
    ),
    "sleep": (
        "indoors", "bedroom", "bed", "on_bed", "pillow", "blanket",
        "sleeping", "lying", "closed_eyes", "soft_lighting",
        "depth_of_field", "blurry_background",
    ),
    "outdoor": (
        "outdoors", "park", "grass", "flower", "walking", "standing",
        "sunlight", "light_rays", "depth_of_field", "blurry_background",
    ),
}


BRANCH_CURATED_SLOT_CANDIDATES = {
    "combat": {
        "setting": ("battlefield", "ruins", "debris", "building", "architecture", "street", "cathedral"),
        "prop": ("weapon", "sword"),
        "action": ("fighting", "holding_sword", "standing", "kneeling"),
        "pose": ("dynamic_pose", "from_below"),
        "atmosphere": ("smoke", "rain", "night", "cloudy", "cinematic_lighting"),
    },
    "travel": {
        "setting": ("city", "street", "downtown", "alley", "building", "architecture", "cathedral", "beach", "sea", "ocean", "hills"),
        "prop": ("backpack", "camera", "umbrella", "bottled_water", "map", "suitcase"),
        "action": ("walking", "looking_back", "holding_camera", "standing"),
        "pose": ("looking_back", "looking_at_viewer", "solo_focus"),
        "atmosphere": ("day", "dusk", "sunset", "rain", "cloudy", "sky"),
    },
    "pool": {
        "setting": ("indoors", "pool", "poolside", "water", "window"),
        "prop": ("lifebuoy",),
        "action": ("holding_swim_ring", "holding", "swimming"),
        "pose": ("standing", "sitting", "looking_at_viewer"),
        "atmosphere": ("soft_lighting", "depth_of_field", "blurry_background"),
    },
    "selfie": {
        "setting": ("indoors", "outdoors", "simple_background"),
        "prop": ("phone", "cellphone", "smartphone"),
        "action": ("holding_phone",),
        "pose": ("selfie", "portrait", "upper_body", "looking_at_viewer"),
        "atmosphere": ("soft_lighting", "depth_of_field", "blurry_background"),
    },
    "leisure": {
        "setting": ("cafeteria", "bedroom", "couch", "fireplace", "classroom", "clubroom", "indoor"),
        "prop": ("food", "sweets", "cup", "teapot", "plate", "tray", "book"),
        "action": ("sitting", "holding_cup", "drinking", "reading", "eating", "holding_book"),
        "pose": ("looking_at_viewer", "smile", "blush"),
        "atmosphere": ("day", "sunlight", "soft_lighting", "warm_atmosphere"),
    },
    "group_play": {
        "setting": ("kindergarten", "classroom", "school", "indoors", "playground"),
        "prop": ("toy", "book", "desk"),
        "action": ("playing", "standing", "walking"),
        "pose": ("looking_at_another", "facing_another"),
        "atmosphere": ("day", "sunlight", "soft_lighting", "depth_of_field"),
    },
    "romance": {
        "setting": ("city", "street", "beach", "sea", "couch", "fireplace", "bedroom"),
        "prop": ("flower", "bouquet", "umbrella", "sweets"),
        "action": ("holding_hands", "hug", "facing_another", "eye_contact", "feeding", "walking"),
        "pose": ("looking_at_another", "facing_another", "eye_contact"),
        "atmosphere": ("sunset", "dusk", "night_sky", "starry_sky", "rain", "cloudy"),
    },
    "kiss": {
        "setting": ("bedroom", "window", "curtains", "couch", "fireplace"),
        "prop": ("pillow", "blanket"),
        "action": ("kiss", "facing_another"),
        "pose": ("closed_eyes", "close-up", "facing_another"),
        "atmosphere": ("soft_lighting", "night", "moonlight", "sunset"),
    },
    "sleep": {
        "setting": ("bedroom", "bed", "on_bed", "pillow", "blanket", "couch"),
        "prop": ("pillow", "blanket"),
        "action": ("sleeping", "lying"),
        "pose": ("lying", "closed_eyes"),
        "atmosphere": ("night", "moonlight", "soft_lighting", "day", "cloudy"),
    },
    "outdoor": {
        "setting": ("nature", "beach", "sea", "ocean", "hills", "city", "street", "building", "architecture", "sky"),
        "prop": ("flower", "bouquet", "umbrella", "backpack"),
        "action": ("walking", "standing", "looking_back"),
        "pose": ("looking_at_viewer", "looking_back"),
        "atmosphere": ("day", "dusk", "sunset", "rain", "cloudy", "starry_sky"),
    },
    "adult": {
        "setting": ("bedroom", "couch", "fireplace", "onsen", "beach", "poolside", "stage", "dressing_room"),
        "prop": (),
        "action": ("lying", "sitting", "dancing", "walking", "bathing"),
        "pose": ("cowboy_shot", "full_body", "looking_at_viewer", "kneeling"),
        "atmosphere": ("soft_lighting", "depth_of_field", "blurry_background", "wet", "sweat", "spotlight", "night"),
    },
}


BRANCH_CURATED_SLOT_COUNTS = {
    "setting": 1,
    "prop": 1,
    "action": 1,
    "pose": 1,
    "atmosphere": 1,
}


SCENE_BRANCH_SUMMARY = {
    "combat": "battle/action scene: battlefield conflict, active spell/weapon motion, strong camera and atmosphere.",
    "travel": "travel/sightseeing scene: city or station route, luggage/camera/map props, walking or looking back.",
    "pool": "pool scene: swimming pool or poolside setting, swimsuit cues, water props, no beach/ocean drift unless explicitly requested.",
    "selfie": "selfie portrait: close/personal framing, phone-held selfie cue, looking at viewer, no travel-camera props by default.",
    "leisure": "daily leisure scene: cafe/tea/picnic/shopping rest, seated or relaxed action, warm everyday lighting.",
    "group_play": "group play scene: main character interacting with surrounding children or friends, classroom/kindergarten setting, no solo portrait drift.",
    "romance": "two-person interaction scene: date/couple framing, hand holding or close interaction, shared gaze, sunset/backlight.",
    "kiss": "kissing scene: two visible characters facing each other, kiss as the locked action, close framing and soft lighting.",
    "sleep": "sleep/rest scene: bedroom or bed setting, sleeping/lying action, closed eyes, pillows/blankets, soft quiet lighting.",
    "outdoor": "general outdoor scene: park/garden/nature/street location, light action, daylight and background depth.",
    "adult": "adult character scene: visible adult subject, body-state tags, simple private setting, no no_humans.",
}


GENERIC_STANDARD_SCENE_TAGS = (
    "indoors", "window", "table", "holding", "sitting", "sunlight",
    "depth_of_field", "blurry_background",
)


GENERIC_INTERACTION_SCENE_TAGS = (
    "indoors", "window", "curtains", "soft_lighting",
    "depth_of_field", "blurry_background",
)


GENERIC_DETAILED_SCENE_TAGS = (
    "indoors", "window", "curtains", "table", "teacup", "book",
    "holding_cup", "drinking", "sitting", "sunlight", "backlighting",
    "depth_of_field", "blurry_background",
)

INTENT_SCENE_PROFILES = dict(INTENT_SCENE_PROFILES)
INTENT_SCENE_PROFILES.setdefault(
    "generic",
    (
        "standing",
    ),
)
INTENT_SCENE_PROFILES.setdefault(
    "bathing",
    (
        "indoors", "bathroom", "bathing", "wet", "bathtub",
        "full_body", "soft_lighting", "depth_of_field", "blurry_background",
    ),
)
INTENT_SCENE_PROFILES.setdefault(
    "pool",
    (
        "indoors", "pool", "water", "swimsuit", "poolside",
        "soft_lighting", "depth_of_field", "blurry_background",
    ),
)
INTENT_SCENE_PROFILES.setdefault(
    "beach",
    (
        "outdoors", "beach", "ocean", "swimsuit", "playing",
        "sunlight", "day", "depth_of_field", "blurry_background",
    ),
)
BRANCH_CURATED_SLOT_CANDIDATES = dict(BRANCH_CURATED_SLOT_CANDIDATES)
BRANCH_CURATED_SLOT_CANDIDATES.setdefault(
    "generic",
    {
        "setting": ("outdoors", "sky", "park", "city", "street", "garden"),
        "prop": ("umbrella", "camera", "book"),
        "action": ("holding", "walking", "looking_back"),
        "pose": ("looking_at_viewer", "upper_body", "cowboy_shot", "standing"),
        "atmosphere": ("soft_lighting", "sunlight", "depth_of_field", "blurry_background", "day", "sunset"),
    },
)
BRANCH_CURATED_SLOT_CANDIDATES.setdefault(
    "bathing",
    {
        "setting": ("indoors", "bathroom", "bathtub", "shower_head"),
        "prop": ("towel",),
        "action": ("bathing", "showering"),
        "pose": ("full_body", "upper_body", "cowboy_shot"),
        "atmosphere": ("wet", "soft_lighting", "depth_of_field", "blurry_background"),
    },
)
BRANCH_CURATED_SLOT_CANDIDATES.setdefault(
    "pool",
    {
        "setting": ("indoors", "pool", "poolside", "water", "window"),
        "prop": ("lifebuoy",),
        "action": ("holding_swim_ring", "holding", "swimming"),
        "pose": ("standing", "sitting", "looking_at_viewer"),
        "atmosphere": ("soft_lighting", "depth_of_field", "blurry_background"),
    },
)
BRANCH_CURATED_SLOT_CANDIDATES.setdefault(
    "beach",
    {
        "setting": ("outdoors", "beach", "ocean", "sea"),
        "prop": ("swimsuit",),
        "action": ("playing", "walking"),
        "pose": ("standing", "looking_at_viewer"),
        "atmosphere": ("sunlight", "day", "depth_of_field", "blurry_background"),
    },
)
BRANCH_CURATED_SLOT_CANDIDATES.update(
    {
        "festival": {
            "setting": ("festival", "street", "paper_lantern", "lantern", "market", "shop"),
            "prop": ("food", "sweets", "umbrella"),
            "action": ("walking", "eating", "holding", "looking_back"),
            "pose": ("full_body", "looking_at_viewer", "looking_back"),
            "atmosphere": ("night", "fireworks", "soft_lighting", "depth_of_field"),
        },
        "stage": {
            "setting": ("stage", "concert", "audience", "spotlight"),
            "prop": ("microphone",),
            "action": ("singing", "dancing"),
            "pose": ("dynamic_pose", "full_body", "from_below"),
            "atmosphere": ("spotlight", "motion_blur", "cinematic_lighting", "depth_of_field"),
        },
        "library": {
            "setting": ("library", "bookshelf", "window", "table"),
            "prop": ("book", "paper"),
            "action": ("reading", "holding_book", "writing"),
            "pose": ("sitting", "upper_body", "looking_at_viewer"),
            "atmosphere": ("sunlight", "soft_lighting", "depth_of_field", "blurry_background"),
        },
        "train_station": {
            "setting": ("train_station", "city", "platform", "sky"),
            "prop": ("suitcase", "backpack", "umbrella"),
            "action": ("walking", "looking_back", "holding"),
            "pose": ("full_body", "looking_back", "solo_focus"),
            "atmosphere": ("rain", "sunset", "cloudy", "depth_of_field"),
        },
        "rooftop": {
            "setting": ("rooftop", "city", "sky", "building"),
            "prop": ("umbrella", "camera"),
            "action": ("standing", "looking_back", "holding"),
            "pose": ("from_below", "full_body", "looking_at_viewer"),
            "atmosphere": ("sunset", "wind", "night_sky", "city_lights"),
        },
        "fantasy_forest": {
            "setting": ("forest", "garden", "flower", "butterfly", "magic_circle"),
            "prop": ("flower",),
            "action": ("walking", "casting_spell", "reaching_towards_viewer"),
            "pose": ("dynamic_pose", "full_body", "looking_at_viewer"),
            "atmosphere": ("light_rays", "magic", "falling_petals", "soft_lighting"),
        },
        "snow": {
            "setting": ("snow", "winter", "street", "city", "sky"),
            "prop": ("umbrella", "scarf"),
            "action": ("walking", "holding", "looking_back"),
            "pose": ("full_body", "looking_at_viewer", "hands_on_lap"),
            "atmosphere": ("cloudy", "soft_lighting", "depth_of_field", "blurry_background"),
        },
        "rainy_street": {
            "setting": ("street", "city", "puddle", "alley", "building"),
            "prop": ("umbrella",),
            "action": ("walking", "holding_umbrella", "looking_back"),
            "pose": ("full_body", "looking_back", "solo_focus"),
            "atmosphere": ("rain", "wet", "night", "city_lights", "depth_of_field"),
        },
        "adult_bedroom": {
            "setting": ("bedroom", "bed", "on_bed", "pillow", "blanket"),
            "prop": ("pillow", "blanket"),
            "action": ("lying", "sitting"),
            "pose": ("full_body", "cowboy_shot", "looking_at_viewer"),
            "atmosphere": ("soft_lighting", "night", "moonlight", "depth_of_field"),
        },
        "adult_lounge": {
            "setting": ("indoors", "couch", "fireplace", "curtains"),
            "prop": ("cup",),
            "action": ("sitting", "drinking", "looking_at_viewer"),
            "pose": ("cowboy_shot", "upper_body", "kneeling"),
            "atmosphere": ("soft_lighting", "warm_atmosphere", "depth_of_field", "blurry_background"),
        },
        "adult_onsen": {
            "setting": ("onsen", "bathroom", "water", "towel"),
            "prop": ("towel",),
            "action": ("bathing", "sitting"),
            "pose": ("full_body", "cowboy_shot", "looking_at_viewer"),
            "atmosphere": ("wet", "steam", "soft_lighting", "depth_of_field"),
        },
        "adult_beach": {
            "setting": ("outdoors", "beach", "ocean", "sea"),
            "prop": ("towel",),
            "action": ("walking", "looking_back"),
            "pose": ("full_body", "looking_at_viewer", "looking_back"),
            "atmosphere": ("sunset", "sunlight", "wet", "depth_of_field"),
        },
        "adult_pool": {
            "setting": ("pool", "poolside", "water"),
            "prop": ("lifebuoy", "towel"),
            "action": ("swimming", "sitting"),
            "pose": ("full_body", "cowboy_shot", "looking_at_viewer"),
            "atmosphere": ("wet", "soft_lighting", "depth_of_field", "blurry_background"),
        },
        "adult_dressing_room": {
            "setting": ("dressing_room", "mirror", "curtains"),
            "prop": ("towel",),
            "action": ("undressing", "standing"),
            "pose": ("full_body", "cowboy_shot", "looking_at_viewer"),
            "atmosphere": ("soft_lighting", "depth_of_field", "blurry_background"),
        },
        "adult_stage": {
            "setting": ("stage", "spotlight", "curtains", "audience"),
            "prop": ("microphone",),
            "action": ("dancing", "singing"),
            "pose": ("dynamic_pose", "full_body", "from_below"),
            "atmosphere": ("spotlight", "cinematic_lighting", "motion_blur", "depth_of_field"),
        },
        "adult_after_battle": {
            "setting": ("ruins", "debris", "battlefield", "smoke"),
            "prop": ("sword",),
            "action": ("kneeling", "standing", "holding_sword"),
            "pose": ("full_body", "from_below", "looking_at_viewer"),
            "atmosphere": ("smoke", "embers", "sparks", "cinematic_lighting"),
        },
    }
)
SCENE_BRANCH_SUMMARY.update(
    {
        "festival": "festival/night-market character scene with lights, stalls, food props, and active walking or eating.",
        "stage": "stage performance character scene with spotlight, microphone, audience, and dynamic movement.",
        "library": "quiet library character scene with books, writing or reading, window light, and composed framing.",
        "train_station": "station travel character scene with luggage, platform motion, weather, and departure mood.",
        "rooftop": "rooftop city character scene with skyline, wind, sunset or night lighting.",
        "fantasy_forest": "fantasy forest character scene with flowers, butterflies, magic, and light rays.",
        "snow": "winter street character scene with snow, cold air, props, and soft depth.",
        "rainy_street": "rainy urban character scene with umbrella, puddles, wet reflections, and night light.",
        "adult_bedroom": "adult character bedroom scene with visible adult subject, bed framing, and intimate lighting.",
        "adult_lounge": "adult character lounge scene with couch/fireplace mood, adult body-state tags, and readable pose.",
        "adult_onsen": "adult character onsen scene with water/steam cues and visible adult subject.",
        "adult_beach": "adult character beach scene with sunset/wet cues and no bathroom drift.",
        "adult_pool": "adult character pool scene with water/poolside cues and no bedroom drift.",
        "adult_dressing_room": "adult character dressing-room scene with mirror/towel cues and no bathroom drift.",
        "adult_stage": "adult character stage scene with performance lighting and dynamic pose.",
        "adult_after_battle": "adult character after-battle scene with ruins, smoke, torn-clothes mood, and cinematic framing.",
    }
)

BRANCH_FREQUENCY_TAG_HINTS = {
    "combat": (
        "battle", "fight", "combat", "weapon", "sword", "gun", "smoke",
        "motion", "dynamic", "ruins", "debris",
    ),
    "battle": (
        "battle", "fight", "combat", "weapon", "sword", "gun", "smoke",
        "motion", "dynamic", "ruins", "debris",
    ),
    "travel": (
        "travel", "street", "city", "station", "airport", "camera", "map",
        "backpack", "suitcase", "walking", "rain", "umbrella", "building",
    ),
    "pool": (
        "pool", "poolside", "swimsuit", "water", "lifebuoy", "swimming",
        "indoors", "window",
    ),
    "selfie": (
        "selfie", "phone", "cellphone", "smartphone", "portrait", "upper_body",
        "looking_at_viewer", "soft",
    ),
    "leisure": (
        "cafe", "coffee", "tea", "cup", "table", "book", "food", "sweets",
        "shopping", "picnic", "sitting", "reading", "casual",
    ),
    "romance": (
        "couple", "date", "heart", "flower", "bouquet", "holding_hands", "hug",
        "eye_contact", "facing_another", "sunset", "soft",
    ),
    "kiss": (
        "kiss", "couple", "facing_another", "closed_eyes", "close-up", "bedroom",
        "window", "curtains", "soft", "moonlight",
    ),
    "sleep": (
        "sleep", "bed", "bedroom", "pillow", "blanket", "lying", "closed_eyes",
        "night", "moonlight", "soft",
    ),
    "bathing": (
        "bath", "bathroom", "shower", "bathtub", "onsen", "wet", "towel",
        "water", "steam",
    ),
    "beach": (
        "beach", "ocean", "sea", "water", "sand", "swimsuit", "bikini",
        "sunlight", "sky", "playing",
    ),
    "outdoor": (
        "outdoor", "park", "garden", "forest", "grass", "flower", "sky",
        "sunlight", "walking", "street",
    ),
    "generic": (),
}
BRANCH_FREQUENCY_TAG_HINTS.update(
    {
        "festival": ("festival", "lantern", "fireworks", "market", "shop", "food", "night"),
        "stage": ("stage", "concert", "spotlight", "microphone", "audience", "dancing", "singing"),
        "library": ("library", "book", "bookshelf", "reading", "writing", "window", "paper"),
        "train_station": ("train", "station", "platform", "suitcase", "backpack", "walking", "rain"),
        "rooftop": ("rooftop", "city", "sky", "building", "wind", "sunset", "night"),
        "fantasy_forest": ("forest", "flower", "butterfly", "magic", "light", "garden"),
        "snow": ("snow", "winter", "street", "umbrella", "cloudy", "scarf"),
        "rainy_street": ("rain", "street", "city", "puddle", "umbrella", "wet", "night"),
        "adult_bedroom": ("bedroom", "bed", "lying", "pillow", "blanket", "soft", "night"),
        "adult_lounge": ("couch", "fireplace", "curtains", "sitting", "soft", "warm"),
        "adult_onsen": ("onsen", "water", "steam", "wet", "towel", "bathing"),
        "adult_beach": ("beach", "ocean", "sea", "water", "wet", "sunset", "walking"),
        "adult_pool": ("pool", "poolside", "water", "wet", "swimming", "towel"),
        "adult_dressing_room": ("dressing", "mirror", "curtains", "undressing", "towel"),
        "adult_stage": ("stage", "spotlight", "curtains", "dancing", "singing", "audience"),
        "adult_after_battle": ("ruins", "debris", "battlefield", "smoke", "embers", "sword"),
    }
)

GENERIC_STANDARD_SCENE_TAGS = (
    "standing",
)
GENERIC_INTERACTION_SCENE_TAGS = (
    "facing_another",
)
GENERIC_DETAILED_SCENE_TAGS = (
    "standing",
)


SETTING_TAG_POOL = {
    "indoors", "outdoors", "classroom", "school", "kindergarten", "window", "curtains",
    "cherry_blossoms", "petals", "flower", "garden", "forest", "plant",
    "grass", "sky", "cloud", "clouds", "mountain", "desk", "table",
    "book", "bookshelf", "library", "tea", "teacup", "cup", "office",
    "paper", "papers", "stage", "concert", "microphone", "audience",
    "shrine", "torii", "beach", "ocean", "snow", "winter", "city",
    "street", "puddle", "paper_lantern", "lantern", "butterfly",
    "umbrella", "sword", "battlefield", "battle", "fighting", "smoke",
    "embers", "sparks", "ruins", "debris", "explosion", "magic_circle",
    "park", "bench", "backpack", "camera", "map", "suitcase",
    "train_station", "airport", "cafe", "shop", "market", "shopping",
    "picnic", "food", "couple", "casual", "pool", "poolside", "lifebuoy",
    "downtown", "alley", "building", "architecture", "skyscraper",
    "cathedral", "cafeteria", "kitchen", "bedroom", "bathroom", "clubroom", "couch",
    "fireplace", "bed", "on_bed", "pillow", "blanket", "nature", "sea", "hills", "underwater", "monster",
    "creature", "bathtub", "shower_head", "onsen", "towel",
}


ACTION_TAG_POOL = {
    "holding", "holding_book", "reading", "holding_cup", "drinking",
    "holding_flower", "holding_pen", "writing", "singing", "jumping",
    "walking", "running", "floating", "casting_spell", "pyrokinesis",
    "reaching_towards_viewer", "outstretched_hand", "holding_umbrella",
    "holding_sword", "dancing", "pointing",
    "battle", "fighting", "playing", "swimming",
    "holding_camera", "holding_phone", "holding_swim_ring", "eating", "holding_hands", "hug",
    "mutual_hug", "hug_from_behind", "cuddling", "arm_hug",
    "facing_another", "eye_contact", "feeding", "sharing_food",
    "sleeping", "lying", "kiss", "whispering", "cooking", "bathing", "showering",
    "princess_carry", "piggyback", "lap_pillow", "shared_umbrella",
    "kabedon", "hand_on_another's_head", "hand_on_another's_cheek",
    "on_ground", "injury", "hitting", "punching", "slapping",
    "praying", "own_hands_together",
}


POSE_TAG_POOL = {
    "upper_body", "full_body", "portrait", "cowboy_shot", "close-up",
    "selfie",
    "standing", "sitting", "kneeling", "hands_on_lap", "dynamic_pose",
    "walking", "running", "jumping",
    "arms_behind_back", "hands_on_own_chest", "looking_back",
    "looking_at_viewer", "looking_at_another", "facing_viewer",
    "from_above", "from_below", "solo_focus", "lying", "closed_eyes",
    "against_wall", "on_ground",
}


ATMOSPHERE_TAG_POOL = {
    "sunset", "evening", "sunlight", "light_rays", "backlighting",
    "falling_petals", "wind", "spotlight", "rain", "wet", "night",
    "moonlight", "fire", "motion_blur", "depth_of_field",
    "blurry_background", "soft_lighting", "cinematic_lighting",
    "smoke", "embers", "sparks", "explosion", "debris", "magic",
    "magic_circle",
    "day", "dusk", "cloudy", "night_sky", "starry_sky", "full_moon",
    "crying", "tears", "injury", "blood", "serious",
    "rolling_eyes", "white_eyes", "empty_eyes", "torn_clothes",
}


EXPRESSION_TAG_POOL = {
    "smile", "gentle_smile", "closed_mouth_smile", "serious", "blush",
    "open_mouth", "closed_mouth", "parted_lips", "closed_eyes", "half-closed_eyes",
    "one_eye_closed", "crying", "tears", "surprised", "angry",
    "embarrassed", "shy", "sleepy", "smirk", "frown",
}


EXPRESSION_TAG_ALLOWLIST = set(EXPRESSION_TAG_POOL) | {
    "happy", "sad", "laughing", "grin", "pout", "annoyed", "confused",
    "scared", "worried", "nervous", "determined", "expressionless",
}


EXPRESSION_TAG_FORBIDDEN_PATTERNS = (
    r"(?:blue|red|green|brown|black|yellow|purple|pink|orange|aqua|grey|gray|golden|amber|heterochromia)_eyes?$",
    r"(?:long|short|messy|curly|straight|blonde|brown|black|white|red|blue|green|pink|purple)_hair$",
)


SCENE_TAG_POOL = (
    SETTING_TAG_POOL
    | ACTION_TAG_POOL
    | POSE_TAG_POOL
    | ATMOSPHERE_TAG_POOL
    | {
    "simple_background", "transparent_background", "white_background",
    "reference_sheet",
    }
)

SETTING_TAG_POOL.update({
    "sakura", "tree", "path", "coffee", "music_room", "rehearsal",
    "guitar", "bass", "bass_guitar", "drums", "volleyball", "sports",
    "sand", "water", "wave", "horizon", "cyberpunk", "futuristic",
    "neon_lights", "reflection", "lake", "fog", "mist", "morning",
    "dojo", "kendo", "shinai", "wooden_sword", "hakama", "kendogi",
    "martial_arts", "video_games", "television", "tv", "game_controller",
    "living_room", "restaurant", "ramen", "bowl", "chopsticks", "serafuku", "school_uniform",
    "campus", "hallway", "corridor", "doctor", "bar", "counter",
    "alcohol", "glass", "translucent", "transparent_background",
    "fan", "suit", "formal", "professional",
    "festival", "fireworks", "platform", "rooftop", "city_lights",
    "scarf", "dressing_room", "mirror", "steam",
})
ACTION_TAG_POOL.update({
    "talking", "bowing", "sparring", "holding_controller",
    "holding_chopsticks", "v_sign", "peace_sign", "performing",
    "holding_glass", "standing", "sitting", "kneeling", "undressing",
})
POSE_TAG_POOL.update({
    "profile", "from_side", "looking_away", "looking_to_the_side",
})
ATMOSPHERE_TAG_POOL.update({
    "stage_lighting", "afternoon", "warm_atmosphere", "fireworks",
    "city_lights", "steam", "sweat", "rim_lighting", "lens_flare",
    "bokeh", "silhouette",
})
SCENE_TAG_POOL = (
    SETTING_TAG_POOL
    | ACTION_TAG_POOL
    | POSE_TAG_POOL
    | ATMOSPHERE_TAG_POOL
    | EXPRESSION_TAG_POOL
    | {
        "simple_background", "transparent_background", "white_background",
        "reference_sheet",
    }
)


TAG_POOL_CATEGORY_HINTS = {
    "setting": (
        "background", "scenery", "location", "room", "street", "city", "school", "classroom", "cafe", "beach",
        "ocean", "sky", "cloud", "garden", "forest", "park", "building", "architecture", "window", "table",
        "bed", "bathroom", "water", "flower", "tree",
    ),
    "action": (
        "holding", "sitting", "standing", "walking", "running", "looking", "smile", "open_mouth", "closed_eyes",
        "reading", "eating", "drinking", "sleeping", "lying", "fighting", "playing", "jumping", "reaching",
    ),
    "pose": (
        "view", "focus", "body", "portrait", "pose", "from", "close-up", "cowboy_shot", "upper_body", "full_body",
        "looking", "standing", "sitting", "lying", "kneeling",
    ),
    "atmosphere": (
        "light", "lighting", "sun", "moon", "night", "day", "shadow", "depth", "blurry", "background", "rain",
        "wet", "wind", "cloud", "smoke", "fire", "spark", "petal", "motion", "cinematic",
    ),
    "expression": (
        "smile", "mouth", "closed_mouth", "open_mouth", "lips", "closed_eyes", "one_eye_closed", "blush",
        "crying", "tears", "angry", "surprised", "embarrassed", "shy", "sleepy", "serious", "frown",
    ),
}


TAG_POOL_FORBIDDEN_FRAGMENTS = (
    "breast", "nipple", "pussy", "penis", "cum", "vagina", "ass", "anus", "sex", "nude", "panties", "underwear","body_writing",
    "hair", "eyes", "eye", "skin", "dress", "skirt", "shirt", "outfit", "clothes", "uniform", "sleeves", "boots",
    "artist", "commentary", "request", "watermark", "signature", "censored", "mosaic", "background",
    "on_body", "under_", "in_mouth",
)


def _standard_pool_tag_allowed(tag, row=None):
    clean = _clean_tag(tag)
    if not clean or clean in canvas_danbooru_policy.QUALITY_TAGS or clean in PLAIN_OUTPUT_TAGS:
        return False
    protected_tags = {
        "1girl", "2girls", "3girls", "4girls", "5girls", "6girls",
        "1boy", "2boys", "3boys", "4boys", "5boys", "6boys",
        "solo", "multiple_others", "no_humans",
    }
    if clean in protected_tags:
        return False
    if len(clean) > 36 or clean.count("_") > 4 or not re.fullmatch(r"[a-z0-9_()'/-]+", clean):
        return False
    if canvas_danbooru_policy.is_named_character_leak_tag(clean):
        return False
    if any(fragment in clean for fragment in TAG_POOL_FORBIDDEN_FRAGMENTS):
        return False
    category = str((row or {}).get("category") or "general")
    if category not in {"general", "meta", "custom"}:
        return False
    group = " ".join(str((row or {}).get(key) or "") for key in ("group", "top_group", "sub_group", "path_group"))
    if re.search(r"NSFW|R-18|禁", group, re.I):
        return False
    return True


def _tag_matches_hints(tag, hints):
    clean = _clean_tag(tag)
    parts = [part for part in clean.split("_") if part]
    for hint in hints or ():
        hint_clean = _clean_tag(hint)
        if not hint_clean:
            continue
        if "_" in hint_clean:
            if clean == hint_clean or clean.startswith(hint_clean + "_") or clean.endswith("_" + hint_clean):
                return True
            continue
        if hint_clean in parts:
            return True
        if hint_clean.endswith("s") and hint_clean[:-1] in parts:
            return True
        if (hint_clean + "s") in parts:
            return True
    return False


def _expression_tag_allowed(tag):
    clean = _clean_tag(tag)
    if not clean:
        return False
    if any(re.fullmatch(pattern, clean) for pattern in EXPRESSION_TAG_FORBIDDEN_PATTERNS):
        return False
    if clean in EXPRESSION_TAG_ALLOWLIST:
        return True
    return _tag_matches_hints(clean, TAG_POOL_CATEGORY_HINTS.get("expression") or ())


def _semantic_pool_tag_allowed(tag, facet, row=None):
    clean = _clean_tag(tag)
    if facet == "expression":
        return _expression_tag_allowed(clean)
    return _standard_pool_tag_allowed(clean, row=row)


def _frequency_csv_tag_rows():
    root = getattr(canvas_danbooru_service, "_CANVAS_DANBOORU_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    paths = (
        os.path.join(root, "tags", "weilin_tagcart.csv"),
        os.path.join(root, "tags", "danbooru_all.csv"),
    )
    rows = []
    for path in paths:
        source = os.path.basename(path)
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as handle:
                for raw in csv.reader(handle):
                    if len(raw) < 3:
                        continue
                    tag = _clean_tag(raw[0])
                    category = str(raw[1] if len(raw) > 1 else "").strip()
                    try:
                        count = int(str(raw[2] if len(raw) > 2 else 0).strip() or 0)
                    except Exception:
                        count = 0
                    rows.append({
                        "tag": tag,
                        "category": {"0": "general", "5": "meta"}.get(category, category or "general"),
                        "count": count,
                        "translation": str(raw[4] if len(raw) > 4 else ""),
                        "group": str(raw[5] if len(raw) > 5 else ""),
                        "top_group": str(raw[5] if len(raw) > 5 else ""),
                        "sub_group": str(raw[6] if len(raw) > 6 else ""),
                        "path_group": str(raw[7] if len(raw) > 7 else ""),
                        "source": source,
                    })
        except Exception:
            continue
    return rows


def _ranked_standard_tag_rows(limit=800):
    rows = []
    try:
        rows.extend(canvas_danbooru_service._canvas_gallery_load_seed_rows(categories=["general"], max_rows=limit))
    except Exception:
        pass
    rows.extend(_frequency_csv_tag_rows())
    best = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        tag = _clean_tag(row.get("tag"))
        if not _standard_pool_tag_allowed(tag, row=row):
            continue
        count = int(row.get("count") or 0)
        current = best.get(tag)
        if current is None or count > int(current.get("count") or 0):
            best[tag] = dict(row, tag=tag, count=count)
    return sorted(best.values(), key=lambda item: int(item.get("count") or 0), reverse=True)


def _expand_story_pools_from_frequency_sources(max_per_facet=80):
    rows = _ranked_standard_tag_rows(limit=1200)
    expanded = {"setting": [], "action": [], "pose": [], "atmosphere": [], "expression": []}
    for row in rows:
        tag = str(row.get("tag") or "")
        clean = _clean_tag(tag)
        if any(fragment in clean for fragment in TAG_POOL_FORBIDDEN_FRAGMENTS):
            continue
        for facet, hints in TAG_POOL_CATEGORY_HINTS.items():
            if len(expanded[facet]) >= max_per_facet:
                continue
            if _semantic_pool_tag_allowed(tag, facet, row=row) and _tag_matches_hints(tag, hints):
                _append_unique(expanded[facet], [tag])
    _append_unique(expanded["expression"], EXPRESSION_TAG_POOL)
    return {key: tuple(value[:max_per_facet]) for key, value in expanded.items()}


@functools.lru_cache(maxsize=1)
def _frequency_pool_expansion_data():
    return _expand_story_pools_from_frequency_sources()


def _random_database_tag_allowed(tag, row=None, adult=False):
    clean = _clean_tag(tag)
    if not clean:
        return False
    if clean in RANDOM_DATABASE_HARD_FORBIDDEN_TAGS:
        return False
    if clean == "text" or clean.endswith("_text") or clean.startswith("text_"):
        return False
    if clean in canvas_danbooru_policy.QUALITY_TAGS or clean in PLAIN_OUTPUT_TAGS:
        return False
    if clean in SUBJECT_COUNT_TAGS or clean in {"solo", "multiple_others", "no_humans"}:
        return False
    if ":" in clean or len(clean) > 48 or clean.count("_") > 5:
        return False
    if not re.fullmatch(r"[a-z0-9_()'/-]+", clean):
        return False
    if re.search(r"_\([^()]+\)$", clean):
        return False
    if canvas_danbooru_policy.is_named_character_leak_tag(clean):
        return False
    if any(fragment in clean for fragment in RANDOM_DATABASE_HARD_FORBIDDEN_FRAGMENTS):
        return False
    if adult and any(fragment in clean for fragment in RANDOM_DATABASE_ADULT_EXTRA_FORBIDDEN_FRAGMENTS):
        return False
    category = str((row or {}).get("category") or "general")
    if category not in {"general", "custom"}:
        return False
    group = " ".join(str((row or {}).get(key) or "") for key in ("group", "top_group", "sub_group", "path_group"))
    if re.search(r"NSFW|R-18|forbidden|forbid", group, re.I):
        return False
    return True


def _random_database_facet_for_row(row):
    tag = _clean_tag((row or {}).get("tag"))
    if not tag:
        return ""
    group = " ".join(str((row or {}).get(key) or "") for key in ("translation", "group", "top_group", "sub_group", "path_group")).lower()
    candidates = []
    for facet, hints in RANDOM_DATABASE_FACET_HINTS.items():
        if _tag_matches_hints(tag, hints) or any(hint in group for hint in hints if len(str(hint)) >= 4):
            candidates.append(facet)
    if "from_" in tag or tag.endswith("_view") or "foreground" in tag or "focus" in tag:
        candidates.append("camera")
    if tag in {"reflection", "silhouette", "motion_blur", "depth_of_field", "blurry_foreground", "wide_shot"}:
        candidates.append("composition")
    if re.search(r"(?:dress|skirt|shirt|jacket|coat|kimono|armor|cloak|hat|scarf|ribbon|boots|gloves)$", tag):
        candidates.append("clothing")
    if re.search(r"(?:sword|weapon|umbrella|book|flower|food|cup|phone|camera|mask|bag|lantern|microphone|mirror)$", tag):
        candidates.append("prop")
    for preferred in ("setting", "action", "pose", "camera", "composition", "atmosphere", "expression", "clothing", "accessory", "prop"):
        if preferred in candidates:
            return preferred
    return ""


def _random_database_ranked_tag_rows(limit=20000):
    rows = []
    try:
        rows.extend(canvas_danbooru_service._canvas_gallery_load_seed_rows(categories=["general"], max_rows=limit))
    except Exception:
        pass
    rows.extend(_frequency_csv_tag_rows())
    best = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        tag = _clean_tag(row.get("tag"))
        if not _random_database_tag_allowed(tag, row=row, adult=False):
            continue
        count = int(row.get("count") or 0)
        current = best.get(tag)
        if current is None or count > int(current.get("count") or 0):
            best[tag] = dict(row, tag=tag, count=count)
    return sorted(best.values(), key=lambda item: int(item.get("count") or 0), reverse=True)


@functools.lru_cache(maxsize=1)
def _random_database_tag_pools():
    rows = _random_database_ranked_tag_rows(limit=20000)
    pools = {facet: [] for facet in RANDOM_DATABASE_FACET_HINTS}
    for row in rows:
        tag = _clean_tag(row.get("tag"))
        if not _random_database_tag_allowed(tag, row=row, adult=False):
            continue
        facet = _random_database_facet_for_row(row)
        if not facet or facet not in pools:
            continue
        if len(pools[facet]) >= RANDOM_DATABASE_POOL_MAX_PER_FACET:
            continue
        _append_unique(pools[facet], [tag])
    for archetype in RANDOM_COMPOSITION_ARCHETYPES.values():
        for tag in archetype.get("tags") or ():
            if _random_database_tag_allowed(tag, {"category": "general"}, adult=False):
                _append_unique(pools.setdefault("composition", []), [tag])
                if tag.startswith("from_") or "focus" in tag or "foreground" in tag:
                    _append_unique(pools.setdefault("camera", []), [tag])
    return {key: tuple(value[:RANDOM_DATABASE_POOL_MAX_PER_FACET]) for key, value in pools.items()}


SFW_ASSOCIATION_SLOT_MAP = {
    "scene": "setting",
    "camera": "camera",
    "pose_action": "action",
    "expression": "expression",
    "clothing": "clothing",
    "prop": "prop",
    "style_light": "atmosphere",
}

SFW_ASSOCIATION_ACTION_HINTS = (
    "holding", "sitting", "standing", "walking", "running", "reading",
    "eating", "drinking", "sleeping", "lying", "fighting", "playing",
    "jumping", "reaching", "dancing", "singing", "floating", "kneeling",
    "looking", "leaning", "turning",
)

SFW_ASSOCIATION_CAMERA_HINTS = (
    "view", "angle", "from_", "focus", "foreground", "close-up",
    "wide", "shot", "pov", "portrait",
)

SFW_ASSOCIATION_FORBIDDEN_FRAGMENTS = (
    "nude", "topless", "nipple", "areola", "pussy", "penis", "vagina",
    "anus", "anal", "cum", "semen", "sex", "fellatio", "deepthroat",
    "irrumatio", "cunnilingus", "handjob", "footjob", "paizuri",
    "masturbation", "fingering", "penetration", "orgasm", "panties",
    "lingerie", "cleavage", "bikini", "swimsuit", "underwear", "crotch",
    "futanari", "pov",
    "armpit", "feet", "soles", "food_on_body",
)

SFW_ASSOCIATION_GENERIC_TRIGGERS = {
    "indoors", "outdoors", "day", "night", "sky", "cloud", "clouds",
    "water", "wet", "window", "tree", "flower", "fire", "cup", "box",
    "holding", "standing", "sitting", "lying", "looking_at_viewer",
    "smile", "blush", "closed_mouth", "open_mouth", "full_body",
    "cowboy_shot", "upper_body", "dress", "shirt", "skirt", "hat",
    "veil", "sweater", "long_sleeves",
}


def _sfw_association_slot_path():
    root = getattr(canvas_danbooru_service, "_CANVAS_DANBOORU_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, "docs", "sfw_trigger_slots.csv")


def _sfw_negative_conflict_path():
    root = getattr(canvas_danbooru_service, "_CANVAS_DANBOORU_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, "docs", "sfw_negative_conflicts.csv")


@functools.lru_cache(maxsize=1)
def _sfw_association_slot_rows():
    path = _sfw_association_slot_path()
    rows = []
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                trigger = _clean_tag(row.get("trigger_tag"))
                related = _clean_tag(row.get("related_tag"))
                slot = str(row.get("slot") or "").strip()
                if not trigger or not related or slot not in SFW_ASSOCIATION_SLOT_MAP:
                    continue
                if any(fragment in trigger or fragment in related for fragment in SFW_ASSOCIATION_FORBIDDEN_FRAGMENTS):
                    continue
                rows.append({
                    "trigger": trigger,
                    "related": related,
                    "slot": slot,
                    "support": _safe_int(row.get("support")),
                    "confidence": _safe_float(row.get("confidence")),
                    "lift": _safe_float(row.get("lift")),
                    "score": _safe_float(row.get("score")),
                })
    except Exception:
        return ()
    rows.sort(key=lambda item: (-float(item.get("score") or 0.0), -int(item.get("support") or 0), item.get("trigger") or "", item.get("related") or ""))
    return tuple(rows)


@functools.lru_cache(maxsize=1)
def _sfw_association_trigger_set():
    return frozenset(
        row.get("trigger")
        for row in _sfw_association_slot_rows()
        if row.get("trigger") and row.get("trigger") not in SFW_ASSOCIATION_GENERIC_TRIGGERS
    )


def _sfw_primary_scene_trigger_tags(*texts):
    triggers = set(_sfw_association_trigger_set())
    output = []
    if not triggers:
        return output
    for text in texts:
        source = str(text or "")
        if not source.strip():
            continue
        for pattern, tags in SCENE_RULES:
            if not re.search(pattern, source, re.I):
                continue
            for tag in tags or ():
                clean = _clean_tag(tag)
                if clean in triggers and clean not in SFW_ASSOCIATION_GENERIC_TRIGGERS:
                    _append_unique(output, [clean])
                    break
    return output


@functools.lru_cache(maxsize=1)
def _sfw_negative_conflict_rows():
    path = _sfw_negative_conflict_path()
    rows = []
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                trigger = _clean_tag(row.get("trigger_tag"))
                related = _clean_tag(row.get("related_tag"))
                if not trigger or not related or trigger == related:
                    continue
                if any(fragment in trigger or fragment in related for fragment in SFW_ASSOCIATION_FORBIDDEN_FRAGMENTS):
                    continue
                rows.append({
                    "trigger": trigger,
                    "related": related,
                    "slot": str(row.get("slot") or "").strip(),
                    "support": _safe_int(row.get("support")),
                    "expected_support": _safe_float(row.get("expected_support")),
                    "lift": _safe_float(row.get("lift"), 1.0),
                    "negative_score": _safe_float(row.get("negative_score")),
                })
    except Exception:
        return ()
    rows.sort(key=lambda item: (-float(item.get("negative_score") or 0.0), item.get("trigger") or "", item.get("related") or ""))
    return tuple(rows)


@functools.lru_cache(maxsize=1)
def _sfw_negative_conflict_lookup():
    lookup = {}
    for row in _sfw_negative_conflict_rows():
        trigger = row.get("trigger")
        related = row.get("related")
        if not trigger or not related:
            continue
        current = lookup.setdefault(trigger, {}).get(related)
        if current is None or float(row.get("negative_score") or 0.0) > float(current.get("negative_score") or 0.0):
            lookup.setdefault(trigger, {})[related] = row
    return lookup


def _sfw_negative_conflict_row(left, right):
    left = _clean_tag(left)
    right = _clean_tag(right)
    if not left or not right or left == right:
        return None
    lookup = _sfw_negative_conflict_lookup()
    return (lookup.get(left) or {}).get(right) or (lookup.get(right) or {}).get(left)


def _sfw_negative_pair_is_strong(left, right, min_score=120.0, max_lift=0.35):
    row = _sfw_negative_conflict_row(left, right)
    if not row:
        return False
    return (
        float(row.get("negative_score") or 0.0) >= float(min_score or 0.0)
        and float(row.get("lift") or 1.0) <= float(max_lift or 1.0)
    )


def _sfw_negative_conflicts_with_any(tag, anchors, min_score=120.0, max_lift=0.35):
    clean = _clean_tag(tag)
    for anchor in anchors or ():
        anchor = _clean_tag(anchor)
        if anchor and anchor != clean and _sfw_negative_pair_is_strong(anchor, clean, min_score=min_score, max_lift=max_lift):
            return True
    return False


def _sfw_association_facet(source_slot, tag):
    slot = str(source_slot or "").strip()
    clean = _clean_tag(tag)
    if slot == "pose_action":
        if any(hint in clean for hint in SFW_ASSOCIATION_CAMERA_HINTS):
            return "camera"
        if any(hint in clean for hint in SFW_ASSOCIATION_ACTION_HINTS):
            return "action"
        return "pose"
    return SFW_ASSOCIATION_SLOT_MAP.get(slot)


def _sfw_prompt_trigger_tags(user_prompt, source_prompt="", scene_tags=None, branch=""):
    triggers = set(_sfw_association_trigger_set())
    if not triggers:
        return []
    output = []
    text_parts = [str(user_prompt or ""), str(source_prompt or ""), str(branch or "")]
    text_parts.extend(str(tag or "") for tag in scene_tags or ())
    explicit_scene_tags = _sfw_primary_scene_trigger_tags(user_prompt, source_prompt)
    text_parts.extend(explicit_scene_tags)
    canonical_scene_tags = {
        _clean_tag(tag)
        for tag in explicit_scene_tags + list(scene_tags or ())
        if _clean_tag(tag) and _clean_tag(tag) not in SFW_ASSOCIATION_GENERIC_TRIGGERS
    }
    for tag in canonical_scene_tags:
        if tag in triggers:
            _append_unique(output, [tag])
    combined = "\n".join(item for item in text_parts if item)
    combined_lookup = _semantic_lookup_key(combined)
    combined_spaced = combined.lower().replace("_", " ")
    for trigger in sorted(triggers, key=lambda item: (-len(item), item)):
        if trigger in output:
            continue
        term = trigger.replace("_", " ")
        term_lookup = _semantic_lookup_key(term)
        if (
            (term and _phrase_term_matches(combined_spaced, term))
            or (term_lookup and re.search(rf"(?<![a-z0-9]){re.escape(term_lookup)}(?![a-z0-9])", combined_lookup))
        ):
            _append_unique(output, [trigger])
    return output


def _sfw_association_slot_candidates(user_prompt, source_prompt="", scene_tags=None, branch="", limit_per_facet=48):
    matched_triggers = set(_sfw_prompt_trigger_tags(user_prompt, source_prompt=source_prompt, scene_tags=scene_tags, branch=branch))
    if not matched_triggers:
        return {}
    combined = "\n".join(str(item or "") for item in (user_prompt, source_prompt, branch) if str(item or "").strip())
    alcohol_requested = bool(re.search(r"\u9152|\u9152\u5427|\u5427\u53f0|\balcohol\b|\bbar\b|\bbeer\b|\bwine\b|\bcocktail\b|\bwhiskey\b|\bsake\b", combined, re.I))
    slots = {key: [] for key in RANDOM_DATABASE_FACET_HINTS}
    for row in _sfw_association_slot_rows():
        if row.get("trigger") not in matched_triggers:
            continue
        tag = _clean_tag(row.get("related"))
        if tag == "alcohol" and not alcohol_requested:
            continue
        if _sfw_negative_conflicts_with_any(tag, matched_triggers, min_score=120.0, max_lift=0.35):
            continue
        if not _random_database_tag_allowed(tag, {"category": "general"}, adult=False):
            continue
        if not _semantic_tag_allowed(tag):
            continue
        facet = _sfw_association_facet(row.get("slot"), tag)
        if not facet or facet not in slots:
            continue
        if len(slots[facet]) >= limit_per_facet:
            continue
        _append_unique(slots[facet], [tag])
    return {slot: tuple(tags[:limit_per_facet]) for slot, tags in slots.items() if tags}


def _sfw_association_tags_for_prompt(user_prompt, source_prompt="", scene_tags=None, branch="", limit=96):
    output = []
    for tags in _sfw_association_slot_candidates(
        user_prompt,
        source_prompt=source_prompt,
        scene_tags=scene_tags,
        branch=branch,
        limit_per_facet=limit,
    ).values():
        _append_unique(output, tags)
    return output[:limit]


def _apply_sfw_negative_conflict_filters(tags, explicit_tags=None, preferred_tags=None, min_score=1600.0, max_lift=0.3, return_removed=False):
    output = []
    removed = []
    explicit = {_clean_tag(tag) for tag in explicit_tags or () if _clean_tag(tag)}
    preferred = {_clean_tag(tag) for tag in preferred_tags or () if _clean_tag(tag)}

    def priority(tag):
        if tag in explicit:
            return 3
        if tag in preferred:
            return 2
        return 1

    for tag in tags or ():
        clean = _clean_tag(tag)
        if not clean:
            continue
        conflict_index = None
        conflict_row = None
        for index, existing in enumerate(output):
            row = _sfw_negative_conflict_row(existing, clean)
            if not row:
                continue
            if (
                float(row.get("negative_score") or 0.0) >= float(min_score or 0.0)
                and float(row.get("lift") or 1.0) <= float(max_lift or 1.0)
            ):
                conflict_index = index
                conflict_row = row
                break
        if conflict_index is None:
            _append_unique(output, [clean])
            continue
        existing = output[conflict_index]
        if priority(clean) > priority(existing):
            removed.append({
                "kept": clean,
                "removed": existing,
                "negative_score": round(float((conflict_row or {}).get("negative_score") or 0.0), 3),
            })
            output.pop(conflict_index)
            _append_unique(output, [clean])
        else:
            removed.append({
                "kept": existing,
                "removed": clean,
                "negative_score": round(float((conflict_row or {}).get("negative_score") or 0.0), 3),
            })
    if return_removed:
        return output, removed
    return output


ASSOCIATION_REVIEW_SFW_SLOT_BUDGETS = {
    "setting": 1,
    "action": 1,
    "pose": 1,
    "atmosphere": 1,
    "expression": 1,
}

ASSOCIATION_REVIEW_ADULT_SLOT_BUDGETS = {
    "camera": 1,
    "atmosphere": 1,
    "expression": 2,
    "body": 1,
}

ASSOCIATION_REVIEW_ADULT_FOCUS_SLOT_BUDGETS = {
    "camera": 1,
    "pose": 3,
    "expression": 2,
    "atmosphere": 1,
}

ASSOCIATION_REVIEW_LOW_VALUE_AUTO_ADD_TAGS = {
    "indoors", "outdoors", "window", "table", "pillow", "on_bed",
    "sitting", "standing", "walking", "holding", "blurry", "closed_mouth",
}

ADULT_FOCUS_UNREQUESTED_SCENE_DRIFT_TAGS = {
    "scenery", "landscape", "outdoors", "wide_shot", "stage", "curtains",
    "ruins", "battlefield", "debris", "smoke", "embers", "building",
    "building_ruins", "rubble_ruins", "sword", "holding_sword",
    "floating_sword", "battle", "fighting",
}

ADULT_FOCUS_UNREQUESTED_NUDITY_TAGS = {
    "nude", "completely_nude", "topless", "bottomless", "nipples",
    "pussy", "pussy/vaginal", "no_panties",
}

ADULT_FOCUS_UNREQUESTED_CHARACTER_DRIFT_TAGS = {
    "catgirl", "cat_girl", "cat_ears", "cat_tail", "rabbit_girl",
    "bunny_girl", "playboy_bunny", "rabbit_ears", "animal_ears", "tail",
    "fox_girl", "wolf_girl",
}

ADULT_FOCUS_UNREQUESTED_DETAIL_DRIFT_TAGS = {
    "anime_style", "bare_shoulders", "cleavage", "closed_lips",
    "delicate_features", "detailed_anatomy", "detailed_face",
    "dreamy_atmosphere", "dynamic_angle", "expressive_face",
    "green_skin", "half_body", "heterochromia", "high_quality",
    "high_resolution", "long_fingernails", "playful_girl",
    "sharp_focus", "slender_waist", "slight_smile", "soft_gaze",
    "vibrant_colors", "white_skin",
}


def _association_review_candidate_tags(candidate_prompt_or_tags):
    if isinstance(candidate_prompt_or_tags, (list, tuple, set)):
        raw_items = list(candidate_prompt_or_tags)
    else:
        raw_items = str(candidate_prompt_or_tags or "").split(",")
    output = []
    for raw in raw_items:
        clean = _clean_tag(raw)
        clean = canvas_danbooru_policy.REPAIR_TAG_ALIASES.get(clean, clean)
        if clean and clean not in output:
            output.append(clean)
    return output


def _association_review_positive_rows(slots, budgets, present_tags, explicit_tags, source):
    present = set(present_tags or ())
    explicit = set(explicit_tags or ())
    rows = []
    selected = []
    for slot, budget in (budgets or {}).items():
        count = 0
        for tag in slots.get(slot) or ():
            clean = _clean_tag(tag)
            if not clean:
                continue
            row = {
                "tag": clean,
                "slot": slot,
                "source": source,
                "present": clean in present,
                "explicit": clean in explicit,
            }
            rows.append(row)
            if (
                clean not in present
                and clean not in explicit
                and clean not in ASSOCIATION_REVIEW_LOW_VALUE_AUTO_ADD_TAGS
                and count < int(budget or 0)
            ):
                selected.append(dict(row, reason=f"{source}:{slot}"))
                present.add(clean)
                count += 1
    return rows[:64], selected[:12]


def _association_review_negative_rows(tags, adult=False, adult_tags=None, explicit_tags=None, preferred_tags=None):
    if adult:
        _filtered, removed = _apply_adult_negative_conflict_filters(
            tags,
            adult_tags=adult_tags,
            explicit_tags=explicit_tags,
            preferred_tags=preferred_tags,
            return_removed=True,
        )
    else:
        _filtered, removed = _apply_sfw_negative_conflict_filters(
            tags,
            explicit_tags=explicit_tags,
            preferred_tags=preferred_tags,
            return_removed=True,
        )
    output = []
    for item in removed or []:
        if not isinstance(item, dict):
            continue
        removed_tag = _clean_tag(item.get("removed"))
        kept_tag = _clean_tag(item.get("kept"))
        if not removed_tag or not kept_tag:
            continue
        output.append({
            "removed": removed_tag,
            "kept": kept_tag,
            "negative_score": round(float(item.get("negative_score") or 0.0), 3),
            "reason": "adult_negative_conflict" if adult else "sfw_negative_conflict",
        })
    return output[:32]


def _association_review_explicit_text_requests(user_prompt, source_prompt=""):
    combined = "\n".join(str(item or "") for item in (user_prompt, source_prompt) if str(item or "").strip())
    output = []
    _append_unique(output, _rule_tags(combined, COMPOSITION_RULES))
    _append_unique(output, _rule_tags(combined, SCENE_RULES))
    _append_unique(output, _rule_tags(combined, ADULT_SCENE_RULES))
    _append_unique(output, _semantic_candidate_tags(user_prompt, ""))
    return output


def build_association_review_context(user_prompt, candidate_prompt="", prompt_intent=None, resolution=None, limit_per_slot=8):
    candidate_tags = _association_review_candidate_tags(candidate_prompt)
    structured_intent = normalize_structured_prompt_intent(prompt_intent)
    locked_tags = list(structured_intent.get("locked_tags") or [])
    source_prompt = "" if _looks_like_compact_tag_prompt(candidate_prompt) else str(candidate_prompt or "")
    if not isinstance(resolution, dict) or not resolution.get("state"):
        try:
            resolution = canvas_danbooru_service._canvas_requested_character_resolution(user_prompt, source_prompt)
        except Exception:
            resolution = {}
    adult_intent = detect_adult_intent(user_prompt, source_prompt)
    adult_tags = list(adult_intent.get("tags") or [])
    adult = bool(adult_tags)
    explicit_tags = []
    _append_unique(explicit_tags, locked_tags)
    _append_unique(explicit_tags, _association_review_explicit_text_requests(user_prompt, source_prompt))
    resolved_tags, copyright_tags = _expanded_identity_tags(user_prompt, source_prompt, resolution or {})
    _append_unique(explicit_tags, resolved_tags)
    _append_unique(explicit_tags, copyright_tags)
    _append_unique(explicit_tags, adult_tags)
    explicit_restore_tags = []
    _append_unique(explicit_restore_tags, _rule_tags(user_prompt, COMPOSITION_RULES))
    if adult:
        _append_unique(explicit_restore_tags, adult_tags)
        _append_unique(explicit_restore_tags, _rule_tags(user_prompt, ADULT_SCENE_RULES))
    else:
        _append_unique(explicit_restore_tags, _rule_tags(user_prompt, SCENE_RULES))
    explicit_additions = [
        {
            "tag": tag,
            "reason": "explicit_user_request",
            "source": "user_request",
        }
        for tag in explicit_restore_tags
        if tag not in set(candidate_tags)
    ][:8]

    positive_rows = []
    selected_additions = []
    triggers = []
    branch = ""
    adult_level = _adult_intent_level(adult_tags, user_prompt, source_prompt) if adult else 0
    adult_focus = False
    slots = {}
    if adult:
        triggers = _adult_prompt_trigger_tags(adult_tags, user_prompt, source_prompt)
        adult_focus = bool(resolved_tags and adult_tags and _adult_named_core_request_only(user_prompt, resolution or {}, adult_tags))
        focus_tags = []
        if adult_focus:
            _append_unique(focus_tags, _adult_focused_context_tags(adult_tags))
            _append_unique(focus_tags, _adult_face_visibility_tags(list(adult_tags) + focus_tags))
            _append_unique(focus_tags, _adult_focused_support_tags(adult_tags))
            focus_slots = {
                "camera": tuple(tag for tag in focus_tags if tag in {"face_focus", "portrait", "upper_body", "close-up"}),
                "pose": tuple(tag for tag in focus_tags if tag in {"on_back", "lying", "spread_legs", "folded"}),
                "expression": tuple(tag for tag in focus_tags if tag in ADULT_EXPRESSION_TAG_ALLOWLIST),
                "atmosphere": tuple(tag for tag in focus_tags if tag in {"soft_lighting", "depth_of_field", "blurry_background"}),
            }
            rows, selected = _association_review_positive_rows(
                focus_slots,
                ASSOCIATION_REVIEW_ADULT_FOCUS_SLOT_BUDGETS,
                candidate_tags,
                explicit_tags,
                "adult_focus",
            )
            positive_rows.extend(rows)
            selected_additions.extend(selected)
        slots = _adult_association_slot_candidates(
            adult_tags,
            user_prompt,
            source_prompt,
            level=adult_level or 1,
            limit_per_slot=limit_per_slot,
        )
        rows, selected = _association_review_positive_rows(
            slots,
            ASSOCIATION_REVIEW_ADULT_FOCUS_SLOT_BUDGETS if adult_focus else ASSOCIATION_REVIEW_ADULT_SLOT_BUDGETS,
            list(candidate_tags) + [item.get("tag") for item in selected_additions if isinstance(item, dict)],
            explicit_tags,
            "adult_association",
        )
        positive_rows.extend(rows)
        if not adult_focus:
            selected_additions.extend(selected)
    else:
        plan = plan_prompt_intent(user_prompt, source_prompt, resolution=resolution)
        branch = str((plan or {}).get("scene_branch") or "").strip()
        scene_tags = list((plan or {}).get("scene_tags") or [])
        triggers = _sfw_prompt_trigger_tags(user_prompt, source_prompt=source_prompt, scene_tags=scene_tags, branch=branch)
        slots = _sfw_association_slot_candidates(
            user_prompt,
            source_prompt=source_prompt,
            scene_tags=scene_tags,
            branch=branch,
            limit_per_facet=limit_per_slot,
        )
        rows, selected = _association_review_positive_rows(
            slots,
            ASSOCIATION_REVIEW_SFW_SLOT_BUDGETS,
            candidate_tags,
            explicit_tags,
            "sfw_association",
        )
        positive_rows.extend(rows)
        selected_additions.extend(selected)

    preferred_tags = [item.get("tag") for item in selected_additions if isinstance(item, dict)]
    negative_rows = _association_review_negative_rows(
        candidate_tags,
        adult=adult,
        adult_tags=adult_tags,
        explicit_tags=explicit_tags,
        preferred_tags=preferred_tags,
    )
    if adult_focus:
        explicit = set(explicit_tags)
        adult_explicit = set(adult_tags)
        for tag in candidate_tags:
            clean = _clean_tag(tag)
            if not clean or clean in explicit:
                continue
            reason = ""
            if clean in ADULT_FOCUS_UNREQUESTED_SCENE_DRIFT_TAGS:
                reason = "adult_focus_scene_drift"
            elif clean == "full_body" and (
                bool(adult_explicit.intersection(ADULT_SPECIFIC_POSITION_TAGS))
                or bool({"upper_body", "portrait", "close-up", "face_focus"}.intersection(explicit))
            ):
                reason = "adult_focus_composition_conflict"
            elif clean in ADULT_FOCUS_UNREQUESTED_NUDITY_TAGS and clean not in adult_explicit:
                reason = "unrequested_adult_nudity"
            elif clean in ADULT_FOCUS_UNREQUESTED_CHARACTER_DRIFT_TAGS:
                reason = "unrequested_character_drift"
            elif clean in ADULT_FOCUS_UNREQUESTED_DETAIL_DRIFT_TAGS:
                reason = "adult_focus_detail_drift"
            elif (
                resolved_tags
                and clean not in ADULT_EXPRESSION_TAG_ALLOWLIST
                and canvas_danbooru_policy.is_named_character_default_detail_tag(clean)
            ):
                reason = "unrequested_named_character_detail"
            if reason:
                negative_rows.append({
                    "removed": clean,
                    "kept": "adult_focus",
                    "negative_score": 9999.0,
                    "reason": reason,
                })

    dedup_negative = []
    seen_negative = set()
    for row in negative_rows:
        key = (row.get("removed"), row.get("kept"), row.get("reason"))
        if key in seen_negative:
            continue
        seen_negative.add(key)
        dedup_negative.append(row)

    return {
        "schema": "simpai.association_review_context.v1",
        "adult": adult,
        "adult_level": adult_level,
        "adult_tags": list(dict.fromkeys(adult_tags))[:16],
        "adult_focus": adult_focus,
        "branch": branch or ("adult_focus" if adult_focus else "adult" if adult else ""),
        "triggers": list(dict.fromkeys(triggers or []))[:16],
        "positive_candidates": positive_rows[:64],
        "selected_additions": selected_additions[:12],
        "explicit_additions": explicit_additions,
        "negative_conflicts": dedup_negative[:32],
        "protected_tags": list(dict.fromkeys(explicit_tags))[:32],
        "candidate_tag_count": len(candidate_tags),
    }


def _random_database_branch_pool(facet, branch, archetype_name="", user_prompt="", source_prompt="", scene_tags=None, adult=False):
    pools = _random_database_tag_pools()
    base_values = list(pools.get(facet) or ())
    association_values = []
    if not adult:
        association_slots = _sfw_association_slot_candidates(
            user_prompt,
            source_prompt=source_prompt,
            scene_tags=scene_tags,
            branch=branch,
        )
        association_values = list(association_slots.get(facet) or ())
    values = list(association_values or base_values)
    if not values:
        return []
    hints = []
    _append_unique(hints, BRANCH_FREQUENCY_TAG_HINTS.get(branch) or ())
    archetype = RANDOM_COMPOSITION_ARCHETYPES.get(str(archetype_name or "")) or {}
    _append_unique(hints, archetype.get("hints") or ())
    for token in re.findall(r"[a-z][a-z0-9_]{2,}", str(user_prompt or "").lower()):
        if token not in {"the", "and", "with", "for", "girl", "boy", "image", "prompt", "draw", "random"}:
            _append_unique(hints, [token])
    if hints:
        matched = [tag for tag in values if _tag_matches_hints(tag, hints)]
        if len(matched) >= 3:
            values = matched
    return [tag for tag in values if _random_database_tag_allowed(tag, {"category": "general"}, adult=adult)]


def _random_composition_archetype(seed_text, branch="", adult=False):
    branch = str(branch or "").strip().lower()
    names = list(RANDOM_COMPOSITION_ARCHETYPES)
    if adult:
        names = [
            name for name in names
            if name not in {"high_angle_overlook", "underwater_float", "floating_magic"}
        ]
    if branch in {"stage", "adult_stage"}:
        names = ["stage_spotlight", "low_angle_dynamic", "foreground_depth", "silhouette_moon"]
    elif branch in {"combat", "adult_after_battle"}:
        names = ["after_battle_ruins", "low_angle_dynamic", "foreground_depth", "silhouette_moon"]
    elif branch in {"rainy_street"}:
        names = ["neon_rain_street", "reflection_scene", "back_view_reveal", "foreground_depth"]
    elif branch in {"pool", "adult_pool", "beach", "adult_beach", "adult_onsen"}:
        names = ["reflection_scene", "foreground_depth", "low_angle_dynamic", "silhouette_moon"]
    elif branch in {"library", "adult_lounge"}:
        names = ["vast_interior", "foreground_depth", "reflection_scene", "high_angle_overlook"]
    return str(_random_choice(names, seed_text, f"composition_archetype:{branch}") or "foreground_depth")


def _random_database_enrichment_count(variation_strength):
    key = str(variation_strength or "balanced").strip().lower()
    if key in {"off", "none", "0", "false", "no"}:
        return 0
    if key in {"light", "low", "1"}:
        return 4
    if key in {"rich", "high", "3"}:
        return 16
    return 12


def _random_database_enrichment_tags(seed_text, branch, archetype_name, user_prompt="", source_prompt="", scene_tags=None, adult=False, variation_strength=None):
    target_total = _random_database_enrichment_count(variation_strength)
    if target_total <= 0:
        return []
    branch = str(branch or "generic").strip().lower() or "generic"
    output = []
    archetype = RANDOM_COMPOSITION_ARCHETYPES.get(str(archetype_name or "")) or {}
    association_slots = {} if adult else _sfw_association_slot_candidates(
        user_prompt,
        source_prompt=source_prompt,
        scene_tags=scene_tags,
        branch=branch,
    )
    if association_slots:
        association_plan = (
            ("setting", 2),
            ("prop", 2),
            ("action", 2),
            ("atmosphere", 1),
            ("expression", 1),
            ("clothing", 1),
            ("camera", 1),
            ("pose", 1),
        )
        for facet, count in association_plan:
            if len(output) >= target_total:
                break
            pool = association_slots.get(facet) or ()
            if not pool:
                continue
            picked = _stable_pick(pool, f"{seed_text}\nsfw_assoc\n{branch}\n{facet}", min(count, target_total - len(output)))
            _append_unique(output, picked)
        _append_unique(output, [
            tag for tag in _stable_pick(archetype.get("tags") or (), f"{seed_text}\nrandom_db_archetype\n{branch}\n{archetype_name}", min(2, max(0, target_total - len(output))))
            if _random_database_tag_allowed(tag, {"category": "general"}, adult=adult)
        ])
    else:
        _append_unique(output, [
            tag for tag in archetype.get("tags") or ()
            if _random_database_tag_allowed(tag, {"category": "general"}, adult=adult)
        ])
    plan = (
        ("setting", 2),
        ("action", 2),
        ("pose", 2),
        ("camera", 2),
        ("composition", 2),
        ("atmosphere", 2),
        ("expression", 1),
        ("clothing", 1),
        ("accessory", 1),
        ("prop", 2),
    )
    for facet, count in plan:
        if len(output) >= target_total:
            break
        pool = _random_database_branch_pool(
            facet,
            branch,
            archetype_name=archetype_name,
            user_prompt=user_prompt,
            source_prompt=source_prompt,
            scene_tags=scene_tags,
            adult=adult,
        )
        if not pool:
            continue
        picked = _stable_pick(pool, f"{seed_text}\nrandom_db\n{branch}\n{archetype_name}\n{facet}", min(count, target_total - len(output)))
        _append_unique(output, picked)
    return _filter_random_branch_conflicts(output[:target_total], branch)


def _limit_random_camera_bias_tags(tags, seed_text, archetype_name, user_prompt="", source_prompt=""):
    values = list(tags or [])
    if "from_below" not in values:
        return values
    combined = "\n".join(item for item in (str(user_prompt or ""), str(source_prompt or "")) if item)
    if re.search(r"(?:from\s+below|low[-_\s]?angle|\u4f4e\u673a\u4f4d|\u4f4e\u89d2\u5ea6|\u4ef0\u89c6|\u4ef0\u8996)", combined, re.I):
        return values
    archetype_name = str(archetype_name or "").strip()
    keep_probability = 0.0
    if archetype_name == "low_angle_dynamic":
        keep_probability = 0.45
    elif archetype_name == "stage_spotlight":
        keep_probability = 0.18
    keep_from_below = bool(
        keep_probability > 0
        and _random_unit_float(seed_text, f"camera_bias:from_below:{archetype_name}") < keep_probability
    )
    if keep_from_below:
        return values
    return [tag for tag in values if tag != "from_below"]


def _limit_random_prompt_tags(tags):
    protected = set(SUBJECT_COUNT_TAGS) | {"solo", "multiple_others", "no_humans"} | set(canvas_danbooru_policy.QUALITY_TAGS)
    output = []
    for tag in tags or ():
        clean = _clean_tag(tag)
        if not clean:
            continue
        if clean in protected:
            _append_unique(output, [clean])
            continue
        if len(output) < RANDOM_DATABASE_PROMPT_TAG_LIMIT:
            _append_unique(output, [clean])
    for tag in tags or ():
        clean = _clean_tag(tag)
        if clean in canvas_danbooru_policy.QUALITY_TAGS and clean not in output:
            _append_unique(output, [clean])
    return output


def _apply_frequency_pool_expansion():
    expanded = _frequency_pool_expansion_data()
    SETTING_TAG_POOL.update(expanded.get("setting") or ())
    ACTION_TAG_POOL.update(expanded.get("action") or ())
    POSE_TAG_POOL.update(expanded.get("pose") or ())
    ATMOSPHERE_TAG_POOL.update(expanded.get("atmosphere") or ())
    EXPRESSION_TAG_POOL.update(expanded.get("expression") or ())
    SCENE_TAG_POOL.update(SETTING_TAG_POOL | ACTION_TAG_POOL | POSE_TAG_POOL | ATMOSPHERE_TAG_POOL | EXPRESSION_TAG_POOL)



SOURCE_STYLE_CARRYOVER_TAGS = {
    "upper_body", "full_body", "portrait", "cowboy_shot", "close-up",
    "looking_at_viewer", "facing_viewer", "smile", "closed_mouth_smile",
    "serious", "serious_expression", "soft_lighting",
    "cinematic_lighting", "depth_of_field", "blurry_background",
}


SOURCE_BRANCH_FORBIDDEN_TAGS = {
    "combat": {
        "smile", "closed_mouth_smile", "holding_flower", "flower",
        "paper_lantern", "lantern", "teacup", "holding_cup",
        "drinking", "sitting", "hands_on_lap",
    },
    "kiss": {
        "looking_at_viewer", "facing_viewer", "smile", "closed_mouth_smile",
        "dynamic_pose", "standing", "walking", "running", "jumping",
        "holding_flower", "holding_camera", "casting_spell",
        "reaching_towards_viewer", "paper_lantern", "lantern",
    },
    "sleep": {
        "looking_at_viewer", "facing_viewer", "smile", "closed_mouth_smile",
        "dynamic_pose", "standing", "sitting", "walking", "running",
        "jumping", "holding_flower", "holding_camera", "casting_spell",
        "reaching_towards_viewer",
    },
}


INTERACTION_LOCK_TAGS = {
    "hug", "mutual_hug", "hug_from_behind", "cuddling", "arm_hug",
    "holding_hands", "facing_another", "looking_at_another", "kiss",
    "lap_pillow", "kabedon", "whispering", "princess_carry", "piggyback",
    "shared_umbrella", "hand_on_another's_head", "hand_on_another's_cheek",
}


PROFILE_LOCK_TAGS = {
    "hug", "mutual_hug", "hug_from_behind", "cuddling", "arm_hug",
    "kiss", "lap_pillow", "kabedon", "whispering", "princess_carry",
    "piggyback", "shared_umbrella", "hand_on_another's_head",
    "hand_on_another's_cheek",
}


ADULT_BLOCKED_CHARACTER_TAGS = {
}


ADULT_CONTEXT_TAGS = (
    "full_body", "soft_lighting", "depth_of_field", "blurry_background",
)

ADULT_FACE_DETAIL_TAGS = (
    "face_focus", "blush", "open_mouth", "half-closed_eyes",
)

ADULT_BACK_POSE_FACE_TAGS = (
    "looking_back", "looking_at_viewer",
)

ADULT_PARTNER_REQUIRED_TAGS = {
    "sex", "penetration", "doggystyle", "missionary", "girl_on_top",
    "cowgirl_position", "clothed_sex", "anal", "cum_inside",
    "oral/fellatio", "oral", "fellatio", "deepthroat", "handjob",
    "irrumatio", "paizuri", "sex_from_behind", "mating_press",
}


ADULT_INTENT_RULES = (
    (r"\u53e3\u4ea4|\u53e3\u7206|\b(?:oral\s+sex|fellatio|blowjob)\b", ("oral/fellatio", "sex", "nude")),
    (r"\u6df1\u5589|\bdeepthroat\b", ("deepthroat", "oral/fellatio", "sex", "nude")),
    (r"\u6253\u624b\u67aa|\u624b\u4ea4|\bhandjob\b", ("handjob", "nude")),
    (r"\u4e73\u4ea4|\bpaizuri\b", ("paizuri", "nude")),
    (r"\u81ea\u6170|\u624b\u6deb|\bmasturbat(?:e|ion)\b", ("masturbation", "nude")),
    (r"\u63d2\u5165|\u62bd\u63d2|\u7834\u74dc|\bpenetrat(?:e|ion)\b", ("penetration", "sex", "nude")),
    (r"\u809b\u4ea4|\u7206\u83ca|\banal(?:\s+sex)?\b", ("anal", "sex", "nude")),
    (r"\u88ab\s*(?:\u64cd|\u809a|\u8279|\u5e72|\u5e79)(?!\u4f5c|\u63a7|\u573a|\u5834|\u7ec3|\u7df4|\u5fc3)|(?:\u64cd|\u809a|\u8279)(?!\u4f5c|\u63a7|\u573a|\u5834|\u7ec3|\u7df4|\u5fc3).{0,4}(?:\u5979|\u4ed6|\u89d2\u8272|\u5973\u5b69|\u5973\u4eba)|\u6027\u4ea4|\u6027\u884c\u4e3a|\u6027\u7231|\u6027\u611b|\u505a\u7231|\u505a\u611b|\u7231\u7231|\u611b\u611b|\u556a\u556a\u556a|\u4ea4\u5408|\u4ea4\u5abe|\u4ea4\u914d|\u540c\u623f|\u53d1\u751f\u5173\u7cfb|\u767c\u751f\u95dc\u4fc2|\bsex\b|\bsexual\s+intercourse\b|\bintercourse\b|\bmake\s+love\b", ("sex", "nude")),
    (r"\u7a7f\u7740\u8863\u670d\u505a\u7231|\u7a7f\u7740\u8863\u670d\u505a\u611b|\bclothed\s+sex\b", ("clothed_sex", "sex")),
    (r"\u4f53\u4f4d|\u6027(?:\u4ea4|\u7231|\u611b)?\u59ff\u52bf|\u6027(?:\u4ea4|\u7231|\u611b)?\u59ff\u52e2|\bsex\s+position\b", ("sex", "nude")),
    (r"\u4f20\u6559\u58eb|\u50b3\u6559\u58eb|\bmissionary\b", ("missionary", "sex", "nude")),
    (r"\u5973\u4e0a\u4f4d|\u9a91\u4e58\u4f4d|\u9a0e\u4e58\u4f4d|\bcowgirl\b|\bgirl\s+on\s+top\b", ("cowgirl_position", "girl_on_top", "sex", "nude")),
    (r"\u72d7\u722c|\u540e\u5165|\u5f8c\u5165|\bdoggystyle\b", ("doggystyle", "sex", "nude")),
    (r"\u6388\u7cbe\u4f53\u4f4d|\u6388\u7cbe\u9ad4\u4f4d|\u4ea4\u914d\u6309\u538b|(?<![a-z0-9_])mating[_\s-]*press(?![a-z0-9_])", ("mating_press", "sex", "penetration", "nude")),
    (r"\u5185\u5c04|\u5167\u5c04|\bcum\s+inside\b", ("cum_inside", "sex", "nude")),
    (r"\u989c\u5c04|\u984f\u5c04|\u5c04\u6ee1\u8138|\u5c04\u6eff\u81c9|\u5c04\u5728(?:\u8138|\u81c9)\u4e0a|\b(?:facial|bukkake|bukake|bukakke|cum\s+on\s+face)\b", ("facial", "bukkake")),
    (r"\u5c04\u7cbe|\u5c04\u51fa|\bcum\b|\bejaculat(?:e|ion)\b", ("cum", "ejaculation", "nude")),
    (r"\u9634\u830e|\u9670\u8396|\u9633\u5177|\u967d\u5177|\u5c4c|\bpenis\b|\bcock\b", ("penis",)),
    (r"\u9634\u6237|\u9670\u6236|\u9634\u90e8|\u9670\u90e8|\u5c0f\u7a74|\bpussy\b|\bvagina(?:l)?\b", ("pussy/vaginal", "nude")),
    (r"\u9634\u6bdb|\u9670\u6bdb|\bpubic\s+hair\b", ("pubic_hair", "nude")),
    (r"\u6f6e\u5439|\bfemale\s+ejaculation\b", ("female_ejaculation", "nude")),
    (r"\u88f8\u4f53|\u5168\u88f8|\u88f8\u9732|\u8d64\u88f8|\u8d64\u8eab|\u4e00\u4e1d\u4e0d\u6302|\u4e00\u7d72\u4e0d\u639b|\u8131\u5149|\u9732\u70b9|\u9732\u9ede|\b(?:nude|naked)\b", ("nude",)),
    (r"\u4e0a\u534a\u8eab\u88f8|\u88f8\u4e0a\u8eab|\btopless\b", ("nipples", "nude")),
    (r"\u4e73\u5934|\u4e73\u982d|\u80f8\u90e8\u88f8\u9732|\bnipples?\b", ("nipples",)),
    (r"\u6478\u80f8|\u63c9\u80f8|\u6293\u80f8|\bbreast\s+grab\b", ("breast_grab", "nude")),
    (r"\u6478\u5c41\u80a1|\u6293\u5c41\u80a1|\u6478\u5c41|\u6293\u5c41|\bass\s+grab\b", ("ass_grab", "nude")),
    (r"(?:r18|r-18|18\+|18\u7981|nsfw)|\u6210\u4eba\u5411|\u6210\u4eba\u56fe|\u6210\u4eba\u5716|\u8272\u60c5|\u60c5\u8272|(?<!\u89d2)\u8272\u56fe|(?<!\u89d2)\u8272\u5716|\u6da9\u56fe|\u6da9\u5716|\u745f\u56fe|\u745f\u5716|\u8272\u8272|\u6da9\u6da9|\u745f\u745f|\u8272\u6c14|\u8272\u6c23|\u8272\u4e00\u70b9|\u8272\u4e00\u9ede|\u6deb\u4e71|\u6deb\u9761|\berotic\b|\bporn(?:ographic)?\b", ("nude",)),
)


ADULT_LEVEL1_SUGGESTIVE_RULES = (
    (r"\u63c9\u80f8|\u6258\u80f8|\u6324\u538b\u80f8|\u80f8\u90e8\u7279\u5199|\u4e73\u6c9f|\bcleavage\b|\bbreast[_\s-]*focus\b|\bbreast[_\s-]*(?:press|hold|lift)\b", ("breast_focus",)),
    (r"\u5c41\u80a1\u7279\u5199|\u80a1\u95f4|\u80a1\u9593|\b(?:ass|butt)[_\s-]*focus\b|\bass[_\s-]*visible[_\s-]*through[_\s-]*thighs\b", ("ass_focus",)),
    (r"\u63c0\u8d77?\u8863|\u63c0\u8863|\u62c9\u8d77?\u8863|\bclothes[_\s-]*lift\b", ("clothes_lift",)),
    (r"\u63c0\u8d77?\u886c\u886b|\u63c0\u886c\u886b|\u886c\u886b\u4e0a\u63d0|\bshirt[_\s-]*lift\b", ("shirt_lift",)),
    (r"\u63c0\u8d77?\u88d9|\u63c0\u88d9|\u88d9\u5b50\u4e0a\u63d0|\bskirt[_\s-]*lift\b", ("skirt_lift",)),
    (r"\u80f8\u7f69\u4e0a\u63d0|\u63c0\u80f8\u7f69|\b(?:bra|sports[_\s-]*bra)[_\s-]*lift\b", ("bra_lift",)),
    (r"\u6bd4\u57fa\u5c3c\u4e0a\u63d0|\u5f80\u4e0a\u5265\u5f00\u7684\u6bd4\u57fa\u5c3c|\bbikini[_\s-]*(?:top[_\s-]*)?lift\b", ("bikini_top_lift",)),
    (r"\u626f\u7740\u6bd4\u57fa\u5c3c|\bbikini[_\s-]*pull\b", ("bikini_pull",)),
    (r"\u6bd4\u57fa\u5c3c(?:\u4e0b\u88c5)?(?:\u632a\u5230|\u62e8\u5230|\u5074\u79fb|\u4fa7\u79fb)\u4e00\u8fb9|\bbikini[_\s-]*bottom[_\s-]*aside\b", ("bikini_bottom_aside",)),
    (r"\u6cf3\u88c5(?:\u632a\u5230|\u62e8\u5230|\u5074\u79fb|\u4fa7\u79fb)\u4e00\u8fb9|\bswimsuit[_\s-]*aside\b", ("swimsuit_aside",)),
    (r"\u900f\u89c6\u88c5|\u900f\u660e\u8863|\bsee[_\s-]*through[_\s-]*(?:clothes|clothing)\b", ("see-through_clothes",)),
    (r"\u900f\u89c6\u886c\u886b|\bsee[_\s-]*through[_\s-]*shirt\b", ("see-through_shirt",)),
    (r"\u900f\u89c6\u5185\u8863|\bsee[_\s-]*through[_\s-]*(?:bra|panties|underwear|lingerie)\b", ("see-through_clothes",)),
    (r"\u900f\u89c6\u6bd4\u57fa\u5c3c|\bsee[_\s-]*through[_\s-]*bikini\b", ("see-through_bikini",)),
    (r"\u900f\u5149\u8f6e\u5ed3|\u900f\u5149\u8f2a\u5ed3|\bsee[_\s-]*through[_\s-]*silhouette\b", ("see-through_silhouette",)),
    (r"\u5185\u8863|\u60c5\u8da3\u5185\u8863|\blingerie\b|\bcat[_\s-]*lingerie\b", ("lingerie",)),
    (r"\u5185\u88e4|\u80d6\u6b21|\bpant(?:y|ies|su)\b|\bwhite[_\s-]*panties\b|\bblack[_\s-]*panties\b|\bwet[_\s-]*panties\b|\bstring[_\s-]*panties\b|\blace(?:[_\s-]*trimmed)?[_\s-]*panties\b", ("panties",)),
    (r"\u771f\u7a7a|\u6ca1\u7a7f\u80f8\u7f69|\u7121\u80f8\u7f69|\u65e0\u80f8\u7f69|\bno[_\s-]*bra\b", ("no_bra",)),
    (r"\u6ca1\u7a7f\u5185\u88e4|\u7121\u5167\u8932|\u65e0\u5185\u88e4|\bno[_\s-]*panties\b", ("no_panties",)),
    (r"\u5185\u88e4(?:\u632a\u5230|\u62e8\u5230|\u5074\u79fb|\u4fa7\u79fb)\u4e00\u8fb9|\bpant(?:y|ies)[_\s-]*aside\b", ("panties_aside",)),
    (r"\u624b\u4f38\u8fdb\u5185\u88e4|\u624b\u5165\u5185\u88e4|\bhand[_\s-]*in[_\s-]*(?:own[_\s-]*)?pant(?:y|ies)\b", ("hand_in_own_panties",)),
    (r"\u89c6\u89d2\u770b\u5411\u88e4\u88c6|\u80ef\u90e8\u89c6\u89d2|\bpov[_\s-]*crotch\b", ("pov_crotch",)),
    (r"\u4fbf\u5229(?:\u6027)?\u6253\u7801|\bconvenient[_\s-]*censor(?:ing|ship)\b", ("convenient_censoring",)),
    (r"\u8d70\u5149|\u80f8\u90e8\u8d70\u5149|\bdown[_\s-]*blouse\b|\bdownblouse\b", ("downblouse",)),
    (r"\u9a86\u9a7c\u8dbe|\u99f1\u99dd\u8dbe|\bcamel[_\s-]*toe\b|\bcameltoe\b", ("cameltoe",)),
    (r"\u9732\u51fa\u4e00\u53ea\u4e73\u623f|\u5355\u4fa7\u9732\u4e73|\u55ae\u5074\u9732\u4e73|\bone[_\s-]*breast[_\s-]*out\b", ("one_breast_out",)),
    (r"\u4e73\u6c9f(?:\u5904)?(?:\u5f00\u6d1e|\u958b\u6d1e|\u955c\u7a7a|\u93e4\u7a7a)|\bcleavage[_\s-]*cutout\b", ("cleavage_cutout",)),
)

ADULT_LEVEL1_SUGGESTIVE_TAGS = frozenset(
    tag
    for _pattern, tags in ADULT_LEVEL1_SUGGESTIVE_RULES
    for tag in tags
)

ADULT_LEVEL1_SUGGESTIVE_ALIASES = {
    "black_panties": "panties",
    "blue_panties": "panties",
    "bow_panties": "panties",
    "cat_lingerie": "lingerie",
    "crotchless_panties": "panties",
    "frilled_bra": "bra",
    "frilled_panties": "panties",
    "hand_in_panties": "hand_in_own_panties",
    "highleg_panties": "panties",
    "lace_panties": "panties",
    "lace-trimmed_panties": "panties",
    "micro_bikini": "bikini",
    "pink_panties": "panties",
    "purple_panties": "panties",
    "red_panties": "panties",
    "see-through": "see-through_clothes",
    "side-tie_panties": "panties",
    "string_panties": "panties",
    "wet_panties": "panties",
    "white_panties": "panties",
}


ADULT_SCENE_RULES = (
    (r"\u6d74\u5ba4|\bbathroom\b", ("indoors", "bathroom", "wet")),
    (r"\u6d17\u6fa1|\u6ce1\u6fa1|\u6c90\u6d74|\u5165\u6d74|\bbath(?:ing)?\b", ("indoors", "bathroom", "bathing", "wet")),
    (r"\u6dcb\u6d74|\u51b2\u6fa1|\bshower(?:ing)?\b", ("bathroom", "showering", "shower_head", "wet")),
    (r"\u6d74\u7f38|\bbathtub\b", ("bathroom", "bathtub", "wet")),
    (r"\u6e29\u6cc9|\bonsen\b|\bhot\s+spring\b", ("onsen", "bathing", "wet")),
    (r"\u6bdb\u5dfe|\btowel\b", ("towel", "wet")),
)


ADULT_LEVEL3_TAGS = {
    "sex", "penetration", "doggystyle", "missionary", "girl_on_top",
    "cowgirl_position", "clothed_sex", "anal", "cum_inside",
    "oral/fellatio", "oral", "fellatio", "deepthroat", "handjob",
    "paizuri", "sex_from_behind", "facial", "bukkake", "mating_press",
}


ADULT_LEVEL2_TAGS = {
    "breast_grab", "ass_grab", "topless", "nipples", "masturbation",
}


ADULT_LEVEL3_BLOCKED_FOR_LEVEL1 = ADULT_LEVEL3_TAGS | {
    "cum", "ejaculation", "penis", "pussy/vaginal", "pubic_hair",
    "female_ejaculation", "handjob", "deepthroat", "anal",
}


ADULT_EXPRESSION_SOFT_TAGS = (
    "blush", "shy", "embarrassed", "smile", "closed_mouth_smile",
    "closed_eyes", "half-closed_eyes",
)


ADULT_EXPRESSION_MEDIUM_TAGS = (
    "open_mouth", "parted_lips", "heavy_breathing", "seductive_smile",
    "smirk", "looking_at_viewer",
)


ADULT_EXPRESSION_EXPLICIT_TAGS = (
    "ahegao", "tongue_out", "drooling", "saliva", "moaning",
)


ADULT_EXPRESSION_TAG_ALLOWLIST = set(ADULT_EXPRESSION_SOFT_TAGS) | set(ADULT_EXPRESSION_MEDIUM_TAGS) | set(ADULT_EXPRESSION_EXPLICIT_TAGS)
ADULT_EXPRESSION_LEVEL2_ONLY = set(ADULT_EXPRESSION_MEDIUM_TAGS)
ADULT_EXPRESSION_LEVEL3_ONLY = set(ADULT_EXPRESSION_EXPLICIT_TAGS)
ADULT_LEVEL3_BLOCKED_FRAGMENTS = (
    "cum", "ejaculation", "penis", "pussy", "vaginal", "anal",
    "deepthroat", "fellatio", "handjob", "paizuri", "sex", "penetrat",
    "cock", "dildo", "vibrator", "sex_toy", "orgasm", "irrumatio",
    "cunnilingus", "footjob",
)


ADULT_POOL_FORBIDDEN_FRAGMENTS = (
    "artist", "commentary", "request", "watermark", "signature", "censored", "mosaic",
    "gore", "rape", "bestial", "animal_penis", "body_writing", "writing_on_body", "text_on_body",
    "child", "children", "loli", "shota", "minor", "kindergarten", "elementary",
    "school", "serafuku", "school_uniform",
    "hair", "eyes", "eye", "skin", "dress", "skirt", "shirt", "outfit", "clothes", "uniform", "sleeves", "boots",
)


ADULT_SLOT_HINTS = {
    "setting": ("bed", "bedroom", "bath", "bathroom", "shower", "onsen", "room", "indoors", "couch"),
    "camera": ("body", "focus", "pov", "view", "close", "from", "portrait"),
    "atmosphere": ("blush", "mouth", "breath", "sweat", "wet", "light", "tears", "saliva"),
    "expression": ("blush", "mouth", "breath", "tears", "saliva", "closed_eyes", "half-closed_eyes", "crying", "shy", "smile", "lips", "seductive", "smirk", "ahegao", "tongue", "drool", "moan"),
    "clothing": ("bikini", "swimsuit", "panties", "bra", "lingerie", "thighhighs", "pantyhose", "cutout", "see-through"),
    "body": ("nude", "topless", "nipples", "breasts", "pussy", "penis", "cum"),
    "contact": ("grab", "kiss", "hug", "touch", "lick", "fondling"),
    "explicit_act": ("sex", "penetration", "fellatio", "handjob", "paizuri", "anal", "missionary", "doggystyle", "cowgirl", "mating_press"),
    "pose": ("lying", "sitting", "kneeling", "spread", "legs", "on_bed", "missionary", "doggystyle", "cowgirl", "mating_press"),
    "prop": ("toy", "dildo", "vibrator", "condom", "towel", "mirror", "pillow", "bed"),
}


ADULT_SAFE_FALLBACK_SLOTS = {
    "setting": ("indoors", "bedroom", "bed", "on_bed", "bathroom", "bathtub"),
    "camera": ("full_body", "cowboy_shot", "upper_body", "face_focus", "close-up"),
    "atmosphere": ("blush", "open_mouth", "half-closed_eyes", "wet", "sweat", "soft_lighting", "depth_of_field", "blurry_background"),
    "expression": ADULT_EXPRESSION_SOFT_TAGS + ADULT_EXPRESSION_MEDIUM_TAGS + ADULT_EXPRESSION_EXPLICIT_TAGS,
    "clothing": ("lingerie", "panties", "bra"),
    "body": ("nude", "topless", "nipples"),
    "contact": ("kiss", "breast_grab", "ass_grab"),
    "explicit_act": ("sex", "penetration", "missionary", "doggystyle", "cowgirl_position", "mating_press"),
    "pose": ("lying", "sitting", "kneeling", "spread_legs"),
    "prop": ("pillow", "towel", "mirror"),
}


RANDOM_IMAGE_INTENT_PATTERNS = (
    r"\u968f\u4fbf",
    r"\u968f\u610f",
    r"\u968f\u673a",
    r"\u96a8\u4fbf",
    r"\u96a8\u610f",
    r"\u96a8\u6a5f",
    r"\u90fd\u884c",
    r"\u54ea\u4e2a\u90fd\u884c",
    r"\u4f60\u51b3\u5b9a",
    r"\u4f60\u6c7a\u5b9a",
    r"\u4efb\u610f",
    r"\u6765\u4e2a\u60ca\u559c",
    r"\u4f86\u500b\u9a5a\u559c",
    r"\b(?:random|whatever|anything|any\s+character|surprise\s+me|up\s+to\s+you|your\s+choice)\b",
)

RANDOM_IMAGE_CONTEXT_PATTERNS = (
    r"\u56fe|\u5716|\u753b|\u756b|\u751f\u6210|\u51fa\u56fe|\u51fa\u5716|\u6765\u4e00\u5f20|\u4f86\u4e00\u5f35|\u6765\u5f20|\u4f86\u5f35|\u5f20\u56fe|\u5f35\u5716|\u89c6\u9891|\u8996\u983b|\u63d0\u793a\u8bcd|\u63d0\u793a\u8a5e|\u89d2\u8272|\u4eba\u7269",
    r"\b(?:draw|image|picture|illustration|prompt|character|generate|create|make)\b",
)

RANDOM_IMAGE_EXPLICIT_SCENERY_PATTERNS = (
    r"\u968f(?:\u4fbf|\u610f|\u673a).{0,12}(?:\u98ce\u666f|\u80cc\u666f|\u573a\u666f|\u58c1\u7eb8)",
    r"(?:random|whatever).{0,24}(?:landscape|scenery|background|wallpaper)",
)

RANDOM_POPULAR_CHARACTER_POOL_LIMIT = 12000
RANDOM_POPULAR_CHARACTER_MIN_COUNT = 100
RANDOM_POPULAR_CHARACTER_HEAD_LIMIT = 260
RANDOM_ADULT_CHARACTER_MIN_COUNT = 500
RANDOM_PERSONA_PROBABILITY = 0.30
RANDOM_DEFAULT_BRANCHES = (
    "leisure", "outdoor", "travel", "combat", "pool", "beach", "sleep",
    "festival", "stage", "library", "train_station", "rooftop",
    "fantasy_forest", "snow", "rainy_street",
)
RANDOM_ADULT_BRANCHES = (
    "adult_bedroom", "adult_lounge", "adult_onsen", "adult_beach",
    "adult_pool", "adult_dressing_room", "adult_stage", "adult_after_battle",
)
RANDOM_NATURAL_STYLE_TAGS = ("anime_style", "illustration", "high_quality")
RANDOM_ADULT_MINOR_RISK_PATTERN = re.compile(
    r"(?:\bloli\b|\bshota\b|\bchild(?:ren)?\b|\bkid\b|\byoung\b|\bminor\b|"
    r"(?:blue_archive|pokemon|kindergarten|elementary|madoka|homura|illya|illyasviel|magical_girl|klee|nahida|qiqi|yaoyao|paimon|nanami_chiaki)|"
    r"\u841d\u8389|\u6b63\u592a|\u5e7c|\u5c0f\u5b66\u751f|\u5c0f\u5b78\u751f|\u672a\u6210\u5e74)",
    re.I,
)
RANDOM_GENERAL_BRANCH_BLOCKED_TAGS = {
    "festival": {"bedroom", "bed", "on_bed", "bathroom", "bathtub", "pool", "poolside"},
    "stage": {"bedroom", "bed", "on_bed", "bathroom", "bathtub", "beach", "ocean", "sea", "pool", "poolside"},
    "library": {"beach", "ocean", "sea", "pool", "poolside", "bathroom", "bathtub", "bedroom", "bed", "on_bed"},
    "train_station": {"beach", "ocean", "sea", "pool", "poolside", "bathroom", "bathtub", "bedroom", "bed", "on_bed"},
    "rooftop": {"beach", "ocean", "sea", "pool", "poolside", "bathroom", "bathtub", "bedroom", "bed", "on_bed"},
    "fantasy_forest": {"city", "street", "alley", "beach", "ocean", "sea", "pool", "poolside", "bathroom", "bathtub", "bedroom", "bed", "on_bed"},
    "snow": {"beach", "ocean", "sea", "pool", "poolside", "bathroom", "bathtub", "beach_umbrella", "swimsuit", "wet_swimsuit"},
    "rainy_street": {"beach", "ocean", "sea", "pool", "poolside", "bathroom", "bathtub", "bedroom", "bed", "on_bed"},
}
RANDOM_ADULT_BRANCH_BLOCKED_TAGS = {
    "adult_bedroom": {"bathroom", "bathtub", "shower_head", "showering", "onsen", "pool", "poolside", "beach", "ocean", "sea"},
    "adult_lounge": {"bathroom", "bathtub", "shower_head", "showering", "onsen", "bedroom", "bed", "on_bed", "pool", "poolside", "beach", "ocean", "sea"},
    "adult_onsen": {"bedroom", "bed", "on_bed", "pillow", "blanket", "couch", "fireplace", "stage", "beach", "ocean", "sea"},
    "adult_beach": {"indoors", "bedroom", "bed", "on_bed", "pillow", "blanket", "bathroom", "bathtub", "shower_head", "onsen", "pool", "poolside", "stage"},
    "adult_pool": {"bedroom", "bed", "on_bed", "pillow", "blanket", "bathroom", "bathtub", "shower_head", "onsen", "beach", "ocean", "sea", "stage"},
    "adult_dressing_room": {"bedroom", "bed", "on_bed", "pillow", "blanket", "bathroom", "bathtub", "shower_head", "onsen", "beach", "ocean", "sea", "pool", "poolside"},
    "adult_stage": {"bedroom", "bed", "on_bed", "pillow", "blanket", "bathroom", "bathtub", "shower_head", "onsen", "beach", "ocean", "sea", "pool", "poolside"},
    "adult_after_battle": {"bedroom", "bed", "on_bed", "pillow", "blanket", "bathroom", "bathtub", "shower_head", "onsen", "beach", "ocean", "sea", "pool", "poolside"},
}
RANDOM_ADULT_GLOBAL_BLOCKED_TAGS = {"water_bottle", "water_gun", "holding_water_gun"}
RANDOM_GENERAL_SPICE_TAGS = (
    "from_above", "dynamic_pose", "looking_back",
    "reaching_towards_viewer", "outstretched_hand", "motion_blur",
    "backlighting", "rim_lighting", "lens_flare", "bokeh",
    "silhouette", "reflection", "wind", "falling_petals",
)
RANDOM_ADULT_SPICE_TAGS = (
    "looking_at_viewer", "cowboy_shot", "full_body",
    "blush", "parted_lips", "half-closed_eyes", "sweat", "wet",
    "backlighting", "soft_lighting", "depth_of_field",
)
RANDOM_POPULAR_CHARACTER_EXCLUDED_TAGS = {
    "sensei_(blue_archive)", "admiral_(kancolle)", "commander_(azur_lane)",
    "producer_(idolmaster)", "doctor_(arknights)", "trainer_(umamusume)",
    "commander_(girls'_frontline)", "master_(fate)", "captain_(honkai_impact)",
    "sensei", "admiral", "commander", "producer", "doctor", "trainer",
    "morichika_rinnosuke", "scaramouche_(genshin_impact)",
}

RANDOM_CHARACTER_BUCKET_ORDER = ("head", "popular", "mid_tail", "long_tail", "wide")
RANDOM_CHARACTER_BUCKET_WEIGHTS = (
    "head",
    "popular", "popular",
    "mid_tail", "mid_tail", "mid_tail",
    "long_tail", "long_tail",
    "wide", "wide",
)

RANDOM_DATABASE_POOL_MAX_PER_FACET = 520
RANDOM_DATABASE_PROMPT_TAG_LIMIT = 52
RANDOM_IMAGE_RESOLUTION_CHOICES = (
    {"key": "portrait_2x3", "template": "SDXL", "aspect_ratio": "832*1216", "width": 832, "height": 1216, "label": "832x1216"},
    {"key": "landscape_3x2", "template": "SDXL", "aspect_ratio": "1216*832", "width": 1216, "height": 832, "label": "1216x832"},
    {"key": "square_1x1", "template": "SDXL", "aspect_ratio": "1024*1024", "width": 1024, "height": 1024, "label": "1024x1024"},
)

RANDOM_DATABASE_HARD_FORBIDDEN_TAGS = {
    "lowres", "bad_id", "bad_pixiv_id", "md5_mismatch",
    "translation_request", "translated", "check_translation",
    "commentary_request", "commentary", "artist_name", "signature",
    "watermark", "sample_watermark", "text", "english_text", "chinese_text",
    "censored", "mosaic_censoring", "bar_censor",
    "group_pose", "stage_connection",
    "depth_charge_projector", "male_underwear", "wet_male_underwear",
    "foreground_text", "animal_focus", "depth_charge",
}

RANDOM_DATABASE_HARD_FORBIDDEN_FRAGMENTS = (
    "artist", "commentary", "request", "watermark", "signature",
    "censored", "mosaic", "lowres", "bad_", "error",
    "meme", "family", "body_switch",
    "hair", "eyes", "eye", "skin",
    "minor",
    "child", "children", "loli", "shota", "kindergarten", "elementary",
    "pokemon", "digimon", "sailor_moon", "junko", "college",
    "futanari", "pov",
    "breast", "nipple", "pussy", "penis", "cum", "vagina", "anus", "crotch", "armpit",
    "sex", "fellatio", "paizuri", "handjob", "masturbation", "rape",
    "footjob", "deepthroat", "irrumatio", "cunnilingus", "orgasm",
    "torture", "gore", "amputation", "vore", "feces", "urine",
    "tentacle", "food_on_body", "from_mouth", "battle_idiot",
    "chest_mouth", "mouth_tentacles",
)

RANDOM_DATABASE_ADULT_EXTRA_FORBIDDEN_FRAGMENTS = (
    "school", "student", "serafuku", "college",
)

RANDOM_DATABASE_FACET_HINTS = {
    "setting": (
        "background", "scenery", "location", "room", "street", "city",
        "school", "cafe", "beach", "ocean", "forest", "park", "building",
        "architecture", "window", "table", "bed", "water", "flower",
        "tree", "sky", "cloud", "station", "rooftop", "stage", "ruins",
        "cathedral", "underwater", "space", "market", "shop",
    ),
    "action": (
        "holding", "sitting", "standing", "walking", "running", "looking",
        "reading", "eating", "drinking", "sleeping", "lying", "fighting",
        "playing", "jumping", "reaching", "dancing", "singing", "floating",
        "casting", "leaning", "turning", "kneeling",
    ),
    "pose": (
        "pose", "body", "portrait", "cowboy_shot", "upper_body", "full_body",
        "close-up", "looking", "standing", "sitting", "lying", "kneeling",
        "from", "focus", "profile",
    ),
    "camera": (
        "view", "angle", "perspective", "from", "focus", "foreground",
        "close-up", "wide", "dutch", "fisheye", "pov", "depth",
    ),
    "composition": (
        "reflection", "silhouette", "foreground", "background", "motion",
        "dynamic", "wide", "symmetry", "profile", "underwater", "floating",
        "depth", "looking_back", "from_behind",
    ),
    "atmosphere": (
        "light", "lighting", "sun", "moon", "night", "day", "shadow",
        "depth", "blurry", "rain", "wet", "wind", "cloud", "smoke",
        "fire", "spark", "petal", "motion", "cinematic", "neon", "fog",
        "mist", "steam", "bokeh", "rim", "glow", "city_lights",
    ),
    "expression": (
        "smile", "mouth", "lips", "eyes", "blush", "crying", "tears",
        "angry", "surprised", "embarrassed", "shy", "sleepy", "serious",
        "frown", "smirk", "laughing", "pout",
    ),
    "clothing": (
        "dress", "skirt", "shirt", "jacket", "coat", "suit", "uniform",
        "kimono", "robe", "armor", "cloak", "hoodie", "sweater",
        "boots", "gloves", "hat", "scarf", "ribbon",
    ),
    "accessory": (
        "weapon", "sword", "gun", "staff", "umbrella", "book", "flower",
        "food", "cup", "phone", "camera", "mask", "bag", "suitcase",
        "lantern", "microphone", "instrument", "mirror",
    ),
    "prop": (
        "weapon", "sword", "umbrella", "book", "flower", "food", "cup",
        "phone", "camera", "bag", "suitcase", "lantern", "microphone",
        "pillow", "blanket", "mirror", "towel", "chair", "bench",
    ),
}

RANDOM_COMPOSITION_ARCHETYPES = {
    "low_angle_dynamic": {
        "tags": ("from_below", "dynamic_pose", "foreshortening", "motion_blur", "cinematic_lighting"),
        "hints": ("from", "below", "dynamic", "motion", "cinematic"),
    },
    "high_angle_overlook": {
        "tags": ("from_above", "looking_up", "wide_shot", "depth_of_field", "cloud"),
        "hints": ("from", "above", "wide", "view", "sky"),
    },
    "back_view_reveal": {
        "tags": ("from_behind", "looking_back", "wind", "blurry_background", "wide_shot"),
        "hints": ("behind", "back", "wind", "wide", "background"),
    },
    "foreground_depth": {
        "tags": ("blurry_foreground", "depth_of_field", "close-up", "solo_focus", "bokeh"),
        "hints": ("foreground", "depth", "close-up", "focus", "bokeh"),
    },
    "reflection_scene": {
        "tags": ("reflection", "water", "puddle", "rain", "wet"),
        "hints": ("reflection", "water", "puddle", "rain", "wet"),
    },
    "underwater_float": {
        "tags": ("underwater", "floating", "water", "bubbles", "light_rays"),
        "hints": ("underwater", "floating", "water", "bubble", "light"),
    },
    "neon_rain_street": {
        "tags": ("neon_lights", "rain", "wet", "reflection", "city_lights"),
        "hints": ("neon", "rain", "wet", "reflection", "city"),
    },
    "stage_spotlight": {
        "tags": ("stage", "spotlight", "stage_lighting", "from_below", "motion_blur"),
        "hints": ("stage", "spotlight", "lighting", "motion"),
    },
    "after_battle_ruins": {
        "tags": ("ruins", "debris", "smoke", "embers", "cinematic_lighting"),
        "hints": ("ruins", "debris", "smoke", "embers", "battle"),
    },
    "vast_interior": {
        "tags": ("indoors", "cathedral", "architecture", "wide_shot", "light_rays"),
        "hints": ("indoor", "cathedral", "architecture", "wide", "light"),
    },
    "silhouette_moon": {
        "tags": ("silhouette", "full_moon", "backlighting", "night_sky", "wind"),
        "hints": ("silhouette", "moon", "backlighting", "night", "wind"),
    },
    "floating_magic": {
        "tags": ("floating", "magic", "magic_circle", "light_particles", "wind"),
        "hints": ("floating", "magic", "light", "wind"),
    },
}


STORY_FACET_MINIMUMS = {
    "standard": {"setting": 2, "action": 1, "pose": 1, "atmosphere": 2},
    "detailed": {"setting": 3, "action": 2, "pose": 1, "atmosphere": 2},
}


STORY_FACET_POOLS = {
    "setting": SETTING_TAG_POOL,
    "action": ACTION_TAG_POOL,
    "pose": POSE_TAG_POOL,
    "atmosphere": ATMOSPHERE_TAG_POOL,
    "expression": EXPRESSION_TAG_POOL,
}


def _clean_tag(tag):
    return canvas_danbooru_policy.clean_prompt_tag_name(tag)


def _append_unique(output, tags):
    for tag in tags or ():
        clean = _clean_tag(tag)
        clean = canvas_danbooru_policy.REPAIR_TAG_ALIASES.get(clean, clean)
        if clean and clean not in output:
            output.append(clean)


RANDOM_WEIGHT_PROTECTED_TAGS = {
    "1girl", "2girls", "3girls", "4girls", "5girls", "6girls",
    "1boy", "2boys", "3boys", "4boys", "5boys", "6boys",
    "solo",
    "multiple_others",
    "no_humans",
    "best_quality",
    "masterpiece",
} | set(canvas_danbooru_policy.QUALITY_TAGS)


RANDOM_WEIGHT_ALLOWED_POOLS = set().union(
    SCENE_TAG_POOL,
    SETTING_TAG_POOL,
    ACTION_TAG_POOL,
    POSE_TAG_POOL,
    ATMOSPHERE_TAG_POOL,
    EXPRESSION_TAG_POOL,
    SOURCE_STYLE_CARRYOVER_TAGS,
    PLAIN_OUTPUT_TAGS,
)


RANDOM_WEIGHT_DENSITY_BY_STRENGTH = {
    "off": 0.0,
    "none": 0.0,
    "light": 0.45,
    "balanced": 0.65,
    "rich": 0.85,
}


RANDOM_WEIGHT_BUCKETS = (
    (0.48, 1.0),
    (0.64, 0.9),
    (0.80, 1.1),
    (0.87, 0.8),
    (0.94, 1.2),
    (0.98, 1.3),
    (1.00, 1.4),
)


_WEIGHTED_TAG_RE = re.compile(r"^\([^:()]+:[0-9.]+\)$")


def _random_weight_seed(user_prompt, source_prompt, tags, prompt_variant_seed=None):
    if prompt_variant_seed not in (None, ""):
        return str(prompt_variant_seed)
    return hashlib.sha256(
        json.dumps(
            {
                "user_prompt": user_prompt,
                "source_prompt": source_prompt,
                "tags": list(tags or []),
                "mode": "danbooru_optional_tag_weights_v1",
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8", "ignore")
    ).hexdigest()[:16]


def _tag_weight_from_digest(digest):
    value = int(str(digest)[:8], 16) / 0xFFFFFFFF
    for ceiling, weight in RANDOM_WEIGHT_BUCKETS:
        if value <= ceiling:
            return weight
    return 1.0


def _random_weight_density(variation_strength):
    key = str(variation_strength or "").strip().lower()
    return RANDOM_WEIGHT_DENSITY_BY_STRENGTH.get(key, 0.38)


def _is_random_weight_candidate(tag, resolved_tags=None, copyright_tags=None):
    raw = str(tag or "").strip()
    if _WEIGHTED_TAG_RE.match(raw):
        return False
    clean = _clean_tag(raw)
    if not clean or clean in RANDOM_WEIGHT_PROTECTED_TAGS:
        return False
    if clean in set(resolved_tags or ()) or clean in set(copyright_tags or ()):
        return False
    if clean in RANDOM_WEIGHT_ALLOWED_POOLS:
        return True
    if re.fullmatch(r"[a-z0-9_]+", clean) and clean not in RANDOM_WEIGHT_PROTECTED_TAGS:
        return True
    return False


def _apply_optional_random_tag_weights(tags, user_prompt, source_prompt="", resolved_tags=None, copyright_tags=None, variation_strength=None, prompt_variant_seed=None):
    seed = _random_weight_seed(user_prompt, source_prompt, tags, prompt_variant_seed)
    density = _random_weight_density(variation_strength)
    if density <= 0:
        output = []
        for tag in tags or []:
            clean = _clean_tag(tag)
            if clean:
                output.append(clean)
        return output
    weighted = []
    for index, tag in enumerate(tags or []):
        clean = _clean_tag(tag)
        if not _is_random_weight_candidate(clean, resolved_tags=resolved_tags, copyright_tags=copyright_tags):
            weighted.append(clean)
            continue
        digest = hashlib.sha256(f"{seed}|{index}|{clean}".encode("utf-8", "ignore")).hexdigest()
        threshold = int(digest[8:16], 16) / 0xFFFFFFFF
        if threshold >= density:
            weighted.append(clean)
            continue
        weight = _tag_weight_from_digest(digest[16:24])
        if weight == 1.0:
            weighted.append(clean)
        else:
            weighted.append(f"({clean}:{weight:.1f})")
    return weighted



def _format_prompt_tag(tag, space_separated_tags=True):
    text = str(tag or "").strip()
    if not text:
        return ""
    match = _WEIGHTED_TAG_RE.match(text)
    if match:
        inner = match.group(0)[1:-1]
        name, weight = inner.rsplit(":", 1)
        if space_separated_tags:
            name = name.replace("_", " ")
        return f"({name}:{weight})"
    if space_separated_tags:
        return text.replace("_", " ")
    return text


def _prompt_text_from_tags(tags, user_prompt, source_prompt="", resolved_tags=None, copyright_tags=None, variation_strength=None, prompt_variant_seed=None, space_separated_tags=True):
    return ", ".join(
        tag for tag in (
            _format_prompt_tag(item, space_separated_tags=space_separated_tags)
            for item in _apply_optional_random_tag_weights(
                tags,
                user_prompt,
                source_prompt=source_prompt,
                resolved_tags=resolved_tags,
                copyright_tags=copyright_tags,
                variation_strength=variation_strength,
                prompt_variant_seed=prompt_variant_seed,
            )
        )
        if tag
    )


def _match_is_negated(source, match):
    if match is None:
        return False
    start = int(match.start() or 0)
    prefix = str(source or "")[max(0, start - 24):start].lower()
    clause = re.split(r"[,，。；;.!?！？\n\r]", prefix)[-1]
    return bool(re.search(
        r"(?:不要|不想|别|別|勿|禁止|无需|無需|no|not|without)\s*(?:给我|給我|画|畫|出现|出現|包含)?\s*$",
        clause,
        re.I,
    ) or re.search(r"(?:不要|不想|别|別|禁止|no|not|without).{0,8}$", clause, re.I))


def _has_positive_pattern(text, pattern):
    source = str(text or "")
    return any(not _match_is_negated(source, match) for match in re.finditer(pattern, source, re.I))


def _rule_tags(text, rules):
    source = str(text or "")
    output = []
    for pattern, tags in rules:
        if _has_positive_pattern(source, pattern):
            _append_unique(output, tags)
    return output


def _has_passive_external_actor_intent(text):
    source = str(text or "").lower()
    if not source:
        return False
    if any(_has_positive_pattern(source, pattern) for pattern in PASSIVE_EXTERNAL_ACTOR_PATTERNS):
        return True
    return False


def _has_passive_attack_intent(text):
    source = str(text or "").lower()
    if not source:
        return False
    return any(_has_positive_pattern(source, pattern) for pattern in PASSIVE_ATTACK_INTENT_PATTERNS)


def _character_name_masked_text(text, resolution=None):
    source = str(text or "")
    if not source:
        return ""
    terms = []
    for row in (resolution or {}).get("resolved") or []:
        if not isinstance(row, dict) or row.get("category") != "character":
            continue
        try:
            values = canvas_danbooru_service._canvas_character_row_lookup_values(row)
        except Exception:
            values = []
        for value in values:
            item = str(value or "").strip()
            if not item:
                continue
            has_cjk = bool(re.search(r"[\u3400-\u9fff]", item))
            min_len = 2 if has_cjk else 3
            if len(item) >= min_len and item not in terms:
                terms.append(item)
    masked = source
    for term in sorted(terms, key=len, reverse=True):
        if re.search(r"[\u3400-\u9fff]", term):
            masked = masked.replace(term, " ")
        else:
            masked = re.sub(rf"(?<![a-z0-9_]){re.escape(term)}(?![a-z0-9_])", " ", masked, flags=re.I)
    return masked


def _has_detail_scene_intent(text):
    source = str(text or "").lower()
    return any(_has_positive_pattern(source, pattern) for pattern in DETAIL_SCENE_PATTERNS)


def _has_plain_scene_intent(text):
    source = str(text or "").lower()
    return any(_has_positive_pattern(source, pattern) for pattern in PLAIN_SCENE_PATTERNS)


def _has_group_other_people_intent(text):
    source = str(text or "").lower()
    return any(_has_positive_pattern(source, pattern) for pattern in GROUP_OTHER_PEOPLE_PATTERNS)


def _has_group_play_scene_intent(text):
    source = str(text or "").lower()
    return any(_has_positive_pattern(source, pattern) for pattern in GROUP_PLAY_SCENE_PATTERNS)


def _has_kindergarten_scene_intent(text):
    source = str(text or "").lower()
    return any(_has_positive_pattern(source, pattern) for pattern in KINDERGARTEN_SCENE_PATTERNS)


def _has_defeated_intent(text):
    source = str(text or "").lower()
    return any(_has_positive_pattern(source, pattern) for pattern in DEFEATED_SCENE_PATTERNS)


def _has_defeated_down_intent(text):
    source = str(text or "").lower()
    return any(_has_positive_pattern(source, pattern) for pattern in DEFEATED_DOWN_PATTERNS)


def _has_kneeling_intent(text):
    source = str(text or "").lower()
    return any(_has_positive_pattern(source, pattern) for pattern in KNEELING_INTENT_PATTERNS)


def _has_battle_damaged_clothing_intent(text):
    source = str(text or "").lower()
    return any(_has_positive_pattern(source, pattern) for pattern in BATTLE_DAMAGED_CLOTHING_PATTERNS)


def _defeated_state_tags_for_text(text):
    output = []
    if _has_kneeling_intent(text):
        _append_unique(output, ["kneeling", "on_ground"])
    elif _has_defeated_down_intent(text):
        _append_unique(output, ["lying", "on_ground"])
    else:
        _append_unique(output, ["kneeling", "on_ground"])
    _append_unique(output, ["injury"])
    if _has_battle_damaged_clothing_intent(text):
        _append_unique(output, ["torn_clothes"])
    return output


def _scene_intent_branch(text):
    source = str(text or "").lower()
    if _has_defeated_intent(source) or any(_has_positive_pattern(source, pattern) for pattern in COMBAT_SCENE_PATTERNS):
        return "combat"
    if any(_has_positive_pattern(source, pattern) for pattern in BATHING_SCENE_PATTERNS):
        return "bathing"
    if any(_has_positive_pattern(source, pattern) for pattern in POOL_SCENE_PATTERNS):
        return "pool"
    if any(_has_positive_pattern(source, pattern) for pattern in BEACH_SCENE_PATTERNS):
        return "beach"
    if any(_has_positive_pattern(source, pattern) for pattern in KISS_SCENE_PATTERNS):
        return "kiss"
    if any(_has_positive_pattern(source, pattern) for pattern in ROMANCE_SCENE_PATTERNS):
        return "romance"
    if _has_group_play_scene_intent(source) or (_has_group_other_people_intent(source) and _has_kindergarten_scene_intent(source)):
        return "group_play"
    if any(_has_positive_pattern(source, pattern) for pattern in SLEEP_SCENE_PATTERNS):
        return "sleep"
    if any(_has_positive_pattern(source, pattern) for pattern in SELFIE_SCENE_PATTERNS):
        return "selfie"
    if any(_has_positive_pattern(source, pattern) for pattern in TRAVEL_SCENE_PATTERNS):
        return "travel"
    if any(_has_positive_pattern(source, pattern) for pattern in LEISURE_SCENE_PATTERNS):
        return "leisure"
    if any(_has_positive_pattern(source, pattern) for pattern in OUTDOOR_SCENE_PATTERNS):
        return "outdoor"
    return ""


def has_pure_scenery_intent(text):
    source = str(text or "").lower()
    if not source:
        return False
    if any(re.search(pattern, source, re.I) for pattern in PURE_SCENERY_EXCLUDE_PATTERNS):
        return False
    return any(re.search(pattern, source, re.I) for pattern in PURE_SCENERY_PATTERNS)


def _resolution_tags(resolution, bucket):
    return [
        _clean_tag(item.get("tag"))
        for item in (resolution or {}).get(bucket) or []
        if isinstance(item, dict) and _clean_tag(item.get("tag"))
    ]


def _identity_index_sets():
    try:
        index = canvas_danbooru_service._canvas_load_danbooru_character_index()
    except Exception:
        index = {}
    return (
        set(index.get("character_tags") or set()) if isinstance(index, dict) else set(),
        set(index.get("copyright_tags") or set()) if isinstance(index, dict) else set(),
    )


def _direct_identity_tags(text):
    character_tags, copyright_tags = _identity_index_sets()
    resolved = []
    copyright = []
    try:
        direct = canvas_danbooru_service._canvas_danbooru_direct_hint_tags(text)
    except Exception:
        direct = []
    for tag in direct or []:
        clean = _clean_tag(tag)
        if not clean:
            continue
        if clean in character_tags:
            _append_unique(resolved, [clean])
        elif clean in copyright_tags:
            _append_unique(copyright, [clean])
    return resolved, copyright


def _expanded_identity_tags(user_prompt, source_prompt, resolution):
    resolved = _resolution_tags(resolution, "resolved")
    copyright = _resolution_tags(resolution, "copyright_candidates")
    direct_resolved, direct_copyright = _direct_identity_tags(user_prompt)
    _append_unique(resolved, direct_resolved)
    _append_unique(copyright, direct_copyright)
    if resolved and not copyright:
        try:
            derived = canvas_danbooru_service._canvas_derive_copyright_hits_from_resolved(
                [{"tag": tag} for tag in resolved],
                canvas_danbooru_service._canvas_load_danbooru_character_index(),
            )
        except Exception:
            derived = []
        _append_unique(copyright, [item.get("tag") for item in derived if isinstance(item, dict)])
    copyright = [
        tag for tag in copyright
        if ":" not in str(tag or "")
    ]
    copyright = canvas_danbooru_policy.drop_redundant_copyright_tags(resolved, copyright)
    return resolved, copyright


def _adult_identity_masked_text(text):
    source = str(text or "")
    if not source:
        return source
    for pattern, _tags in tuple(ADULT_INTENT_RULES) + tuple(ADULT_LEVEL1_SUGGESTIVE_RULES):
        source = re.sub(pattern, " ", source, flags=re.I)
    return re.sub(r"\s+", " ", source).strip()


def _source_safe_tags(source_prompt, include_scene=False):
    if include_scene:
        safe_tags = set(getattr(canvas_danbooru_policy, "NAMED_CHARACTER_SAFE_SOURCE_TAGS", set()))
        safe_tags.update(SCENE_TAG_POOL)
    else:
        safe_tags = set(SOURCE_STYLE_CARRYOVER_TAGS)
    output = []
    for raw in str(source_prompt or "").split(","):
        clean = _clean_tag(raw)
        clean = canvas_danbooru_policy.REPAIR_TAG_ALIASES.get(clean, clean)
        if not clean or clean in canvas_danbooru_policy.QUALITY_TAGS:
            continue
        if clean in PLAIN_OUTPUT_TAGS:
            continue
        if canvas_danbooru_policy.is_named_character_leak_tag(clean):
            continue
        if canvas_danbooru_policy.is_named_character_default_detail_tag(clean):
            continue
        if clean in safe_tags:
            _append_unique(output, [clean])
    return output


def _transparent_background_requested(user_prompt="", source_prompt="", intent=None, tags=None):
    tag_set = set(tags or ())
    if "transparent_background" in tag_set:
        return True
    intent = intent or {}
    if "transparent_background" in set(intent.get("scene_tags") or ()):
        return True
    combined = "\n".join(item for item in (str(user_prompt or ""), str(source_prompt or "")) if item)
    return bool(re.search(
        r"\u900f\u660e\u80cc\u666f|\u80cc\u666f.{0,6}\u900f\u660e|\u900f\u660e\u5e95|\u900f\u660e\u5e95\u8272|\u65e0\u80cc\u666f|\u53bb\u80cc\u666f|\u62a0\u56fe|\u6263\u56fe|\btransparent\s+background\b|\bno\s+background\b",
        combined,
        re.I,
    ))


def _copyright_scopes_from_resolved_tags(resolved_tags):
    scopes = set()
    for tag in resolved_tags or ():
        clean = _clean_tag(tag)
        match = re.search(r"_\(([^()]+)\)$", clean)
        if not match:
            continue
        scoped = _clean_tag(match.group(1))
        scoped = canvas_danbooru_policy.REPAIR_TAG_ALIASES.get(scoped, scoped)
        if scoped:
            scopes.add(scoped)
    return scopes


COMMON_SCENE_IDENTITY_ROOT_TAGS = {
    "city", "street", "road", "alley", "landscape", "scenery", "background",
    "outdoors", "indoors", "garden", "forest", "park", "grass", "flower",
    "sky", "cloud", "clouds", "rain", "night", "puddle", "reflection",
    "water", "beach", "ocean", "sea", "mountain", "lake",
}


def _common_scene_identity_shadow_tag(tag):
    clean = _clean_tag(tag)
    return bool(clean and any(clean.startswith(root + "_(") for root in COMMON_SCENE_IDENTITY_ROOT_TAGS))


def _filter_unrequested_common_scene_identity_tags(tags, user_prompt=""):
    user_key = _semantic_lookup_key(user_prompt)
    output = []
    for tag in tags or []:
        clean = _clean_tag(tag)
        if not clean:
            continue
        if _common_scene_identity_shadow_tag(clean) and (not user_key or _semantic_lookup_key(clean) not in user_key):
            continue
        if clean not in output:
            output.append(clean)
    return output


def _canonical_tag_protected(tag, resolved_tags=None, copyright_tags=None, subject_count_tags=None):
    clean = _clean_tag(tag)
    if not clean:
        return False
    if clean in set(resolved_tags or ()) or clean in set(copyright_tags or ()):
        return True
    if clean in set(subject_count_tags or ()):
        return True
    if clean in {"solo", "multiple_others", "no_humans"}:
        return True
    if clean in canvas_danbooru_policy.QUALITY_TAGS:
        return True
    if clean in PLAIN_OUTPUT_TAGS:
        return True
    return False


def _canonical_tag_allowed(tag, resolved_tags=None, copyright_tags=None, subject_count_tags=None):
    clean = _clean_tag(tag)
    if not clean:
        return False
    if clean in {"none", "null", "nil", "na", "n/a"}:
        return False
    if _canonical_tag_protected(clean, resolved_tags=resolved_tags, copyright_tags=copyright_tags, subject_count_tags=subject_count_tags):
        return True
    if _common_scene_identity_shadow_tag(clean):
        return False
    if ":" in str(tag or "") or ":" in clean:
        return False
    if len(clean) > 64:
        return False
    if clean.count("_") >= 6:
        allowed = set().union(
            SCENE_TAG_POOL,
            SOURCE_STYLE_CARRYOVER_TAGS,
            _curated_tagcart_tag_set(),
            set(_danbooru_general_tag_lookup().values()),
        )
        if clean not in allowed:
            return False
    if re.search(r"[^a-z0-9_()'!/.-]", clean):
        return False
    return True


def _blue_archive_student_request_text(user_prompt="", source_prompt=""):
    combined = "\n".join(item for item in (str(user_prompt or ""), str(source_prompt or "")) if item).lower()
    if not re.search(r"blue\s*archive|\u84dd\u8272\u6863\u6848|\u78a7\u84dd\u6863\u6848|\u851a\u84dd\u6863\u6848", combined, re.I):
        return False
    return bool(re.search(
        r"\u54ea\u4e2a\u5b66\u751f|\u4efb\u610f\u5b66\u751f|\u968f\u4fbf.{0,8}\u5b66\u751f|\u90fd\u884c|\bany\s+student\b|\brandom\s+student\b|\bwhatever\s+student\b",
        combined,
        re.I,
    ))


def _has_selfie_intent(text):
    source = str(text or "").lower()
    return any(_has_positive_pattern(source, pattern) for pattern in SELFIE_SCENE_PATTERNS)


def _apply_selfie_scene_filters(output, intent):
    branch = str((intent or {}).get("scene_branch") or "").strip().lower()
    explicit_scene_tags = set((intent or {}).get("scene_tags") or [])
    if branch != "selfie" and "selfie" not in explicit_scene_tags:
        return output
    blocked = {
        "camera", "holding_camera", "taking_picture", "backpack", "suitcase",
        "map", "walking", "looking_back",
    }
    output[:] = [tag for tag in output if tag not in blocked]
    _append_unique(output, ["selfie", "holding_phone", "portrait", "looking_at_viewer"])
    return output


def _restore_final_hard_intent_tags(output, user_prompt="", source_prompt="", intent=None):
    combined = "\n".join(item for item in (str(user_prompt or ""), str(source_prompt or "")) if item)
    tag_set = set(output or ())
    if (
        tag_set.intersection({"city", "street"})
        and tag_set.intersection({"walking", "looking_back"})
        and not _has_selfie_intent(combined)
        and re.search(r"\u8fb9\u8d70\u8fb9\u62cd|\u62cd\u6444|\u62cd\u7167|\u65c5\u884c\u7167|\btravel\s+photo\b|\bphoto\b|\bcamera\b", combined, re.I)
    ):
        _append_unique(output, ["camera", "holding_camera"])
    if tag_set.intersection({"battle", "battlefield", "fighting"}) and re.search(
        r"\u8054\u624b.{0,8}\u6218\u6597|\u534f\u529b.{0,8}\u6218\u6597|\bteam(?:ed)?\s+up\b.*\b(?:battle|fight|combat)\b|\b(?:battle|fight|combat)\b.*\btogether\b",
        combined,
        re.I,
    ):
        _append_unique(output, ["monster", "creature"])
    if _has_defeated_intent(combined):
        _append_unique(output, _defeated_state_tags_for_text(combined))
    if _has_passive_external_actor_intent(combined):
        output[:] = [tag for tag in output if tag != "solo"]
        if (
            "no_humans" not in set(output)
            and set(output).intersection({"1girl", "1boy"})
            and not _subject_count_implies_multiple(output)
        ):
            _append_unique(output, ["multiple_others"])
    if _has_passive_attack_intent(combined):
        output[:] = [tag for tag in output if tag != "solo"]
        _append_unique(output, ["facing_another", "fighting", "hitting", "injury"])
    if re.search(r"\u7ffb\u767d\u773c|\broll(?:ed|ing)?\s+eyes?\b", combined, re.I):
        _append_unique(output, ["rolling_eyes", "white_eyes", "empty_eyes"])
    if _has_battle_damaged_clothing_intent(combined):
        _append_unique(output, ["torn_clothes"])
    if "lake" in tag_set and ("mountain" in tag_set or re.search(r"\u5c71|\bmountain\b", combined, re.I)) and not tag_set.intersection({"tree", "forest"}):
        _append_unique(output, ["tree", "forest"])
    if (
        tag_set.intersection({"sky", "cloud", "clouds", "mountain"})
        and not tag_set.intersection({"sunlight", "light_rays", "night", "moonlight", "sunset", "rain"})
    ):
        _append_unique(output, ["sunlight"])
    if _blue_archive_student_request_text(user_prompt, source_prompt):
        if "1girl" in tag_set:
            output[:] = [tag for tag in output if tag != "solo"]
        _append_unique(output, ["blue_archive", "student", "school_uniform", "campus", "walking", "outdoors", "sky", "day"])


def _sanitize_final_canonical_tags(
    tags,
    user_prompt,
    source_prompt="",
    resolved_tags=None,
    copyright_tags=None,
    intent=None,
    subject_count_tags=None,
):
    output = []
    resolved_tags = list(resolved_tags or ())
    copyright_tags = list(copyright_tags or ())
    subject_count_tags = list(subject_count_tags or ())
    scoped_copyright = _copyright_scopes_from_resolved_tags(resolved_tags)
    subject_count_set = set(subject_count_tags)
    has_locked_subject_count = bool(subject_count_set)
    for raw in tags or ():
        clean = _clean_tag(raw)
        clean = canvas_danbooru_policy.REPAIR_TAG_ALIASES.get(clean, clean)
        if not _canonical_tag_allowed(clean, resolved_tags=resolved_tags, copyright_tags=copyright_tags, subject_count_tags=subject_count_tags):
            continue
        if has_locked_subject_count and clean in SUBJECT_COUNT_TAGS and clean not in subject_count_set:
            continue
        if scoped_copyright and clean in scoped_copyright and clean not in set(copyright_tags):
            continue
        _append_unique(output, [clean])

    if has_locked_subject_count:
        front = []
        _append_unique(front, subject_count_tags)
        _append_unique(front, [tag for tag in output if tag not in SUBJECT_COUNT_TAGS])
        output = front
    if _subject_count_implies_multiple(subject_count_tags or output):
        output = [tag for tag in output if tag != "solo"]

    if _transparent_background_requested(user_prompt, source_prompt, intent=intent, tags=output):
        _append_unique(output, ["transparent_background"])
        if not set(output).intersection({"upper_body", "portrait", "cowboy_shot", "close-up"}):
            _append_unique(output, ["full_body"])
        _append_unique(output, ["standing"])

    _restore_final_hard_intent_tags(output, user_prompt=user_prompt, source_prompt=source_prompt, intent=intent)

    output = _apply_user_explicit_conflict_filters(output, intent or {})
    output = _apply_indoor_scene_conflict_filters(output, intent or {})
    output = _apply_bathing_scene_conflict_filters(output, intent or {})
    output = _apply_bed_scene_conflict_filters(output, intent or {})
    output = _apply_beach_scene_conflict_filters(output, intent or {})
    output = _apply_street_scene_conflict_filters(output, intent or {})
    output = _apply_major_scene_conflict_filters(output, intent or {})
    return output


def _facet_counts(tags):
    tag_set = set(tags or [])
    return {
        name: len(tag_set.intersection(pool))
        for name, pool in STORY_FACET_POOLS.items()
    }


def _scene_tag_count(tags):
    return sum(1 for tag in tags or [] if tag in SCENE_TAG_POOL)


def _needs_story_enrichment(tags, intent):
    if not intent or intent.get("plain_scene"):
        return False
    mode = "detailed" if intent.get("detail_scene") else "standard"
    minimums = STORY_FACET_MINIMUMS.get(mode, STORY_FACET_MINIMUMS["standard"])
    counts = _facet_counts(tags)
    return any(int(counts.get(name) or 0) < int(minimum or 0) for name, minimum in minimums.items())


def _ensure_story_facets(output, profile_tags, intent):
    if not output or not intent or intent.get("plain_scene"):
        return
    branch = str(intent.get("scene_branch") or "generic").strip().lower() or "generic"
    mode = "detailed" if intent.get("detail_scene") else "standard"
    minimums = STORY_FACET_MINIMUMS.get(mode, STORY_FACET_MINIMUMS["standard"])
    candidates = BRANCH_CURATED_SLOT_CANDIDATES.get(branch) or BRANCH_CURATED_SLOT_CANDIDATES.get("generic") or {}
    seed_text = json.dumps(
        {
            "branch": branch,
            "mode": mode,
            "scene_tags": intent.get("scene_tags") or [],
            "composition_tags": intent.get("composition_tags") or [],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    for facet, minimum in minimums.items():
        if facet == "setting":
            slot_pool = candidates.get("setting") or ()
        else:
            slot_pool = candidates.get(facet) or ()
        count = int(_facet_counts(output).get(facet) or 0)
        if count >= int(minimum or 0):
            continue
        for tag in _stable_pick(slot_pool, seed_text + "\n" + facet, int(minimum or 0) - count):
            if _semantic_tag_allowed(tag):
                _append_unique(output, [tag])


def _detail_profile_tags(resolved_tags, copyright_tags):
    return []


def _standard_profile_tags(resolved_tags, copyright_tags):
    return []


def _intent_profile_tags(intent):
    if not intent or intent.get("plain_scene"):
        return []
    branch = str(intent.get("scene_branch") or "generic").strip().lower() or "generic"
    return list(INTENT_SCENE_PROFILES.get(branch) or INTENT_SCENE_PROFILES.get("generic") or ())


def _intent_has_defeated_state(intent):
    if not intent:
        return False
    defeated_tags = {"kneeling", "lying", "on_ground", "injury", "torn_clothes", "rolling_eyes", "white_eyes", "empty_eyes"}
    return bool(set((intent or {}).get("scene_tags") or ()).intersection(defeated_tags))


@functools.lru_cache(maxsize=1)
def _curated_tagcart_tag_set():
    output = set()
    root = getattr(canvas_danbooru_service, "_CANVAS_DANBOORU_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(root, "tags", "weilin_tagcart.csv")
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            for raw in csv.reader(handle):
                if not raw:
                    continue
                top_group = str(raw[5] if len(raw) > 5 else "")
                if "NSFW" in top_group:
                    continue
                clean = _clean_tag(raw[0])
                clean = canvas_danbooru_policy.REPAIR_TAG_ALIASES.get(clean, clean)
                if not clean or clean in canvas_danbooru_policy.QUALITY_TAGS:
                    continue
                if clean in PLAIN_OUTPUT_TAGS:
                    continue
                if canvas_danbooru_policy.is_named_character_leak_tag(clean):
                    continue
                if canvas_danbooru_policy.is_named_character_default_detail_tag(clean):
                    continue
                # The curated file contains a few prose prompt snippets; keep this pool tag-like.
                if "," in clean or len(clean) > 36 or clean.count("_") > 4:
                    continue
                output.add(clean)
    except Exception:
        return set()
    return output


def _tagcart_tag_candidates(raw_tag):
    output = []
    for item in re.split(r"[/|]", str(raw_tag or "")):
        clean = _clean_tag(item)
        clean = canvas_danbooru_policy.REPAIR_TAG_ALIASES.get(clean, clean)
        if clean and clean not in output:
            output.append(clean)
    return output


@functools.lru_cache(maxsize=1)
def _adult_tagcart_allowlist_data():
    allowlist = set()
    lookup = {}
    phrase_terms = []
    root = getattr(canvas_danbooru_service, "_CANVAS_DANBOORU_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(root, "tags", "weilin_tagcart.csv")
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.reader(handle):
                if not row:
                    continue
                top_group = str(row[5] if len(row) > 5 else "")
                if "NSFW" not in top_group.upper():
                    continue
                tags = _tagcart_tag_candidates(row[0])
                tags = [
                    tag for tag in tags
                    if tag
                    and tag not in canvas_danbooru_policy.QUALITY_TAGS
                    and tag not in PLAIN_OUTPUT_TAGS
                    and not canvas_danbooru_policy.is_named_character_leak_tag(tag)
                ]
                if not tags:
                    continue
                primary = tags[-1] if len(tags) > 1 else tags[0]
                for tag in tags:
                    allowlist.add(tag)
                    key = _semantic_lookup_key(tag)
                    if key:
                        lookup.setdefault(key, tag)
                translation = str(row[4] if len(row) > 4 else "")
                for item in re.split(r"[,|/，、；;()（）]", translation):
                    term = str(item or "").strip()
                    key = _semantic_lookup_key(term)
                    if key:
                        lookup.setdefault(key, primary)
                    if term and len(term) >= 2:
                        phrase_terms.append((term.lower(), primary))
    except Exception:
        return frozenset(), {}, tuple()
    return frozenset(allowlist), lookup, tuple(phrase_terms)


def _semantic_lookup_key(value):
    source = str(value or "").strip().lower()
    source = source.replace("（", "(").replace("）", ")")
    return re.sub(r"[\s_\-,'\"`~!@#$%^&*+=:;./\\|?<>\[\]{}()]+", "", source)


def _semantic_lookup_term_allowed_for_tag(term, tag):
    clean_tag = _clean_tag(tag)
    key = _semantic_lookup_key(term)
    if clean_tag == "green_blood" and key not in {"greenblood", "\u7eff\u8272\u8840\u6db2", "\u7eff\u8840"}:
        return False
    return True


@functools.lru_cache(maxsize=1)
def _danbooru_general_tag_lookup():
    lookup = {}
    root = getattr(canvas_danbooru_service, "_CANVAS_DANBOORU_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(root, "tags", "danbooru_all.csv")
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.reader(handle):
                if not row:
                    continue
                tag = _clean_tag(row[0])
                category = str(row[1] if len(row) > 1 else "")
                translation = str(row[4] if len(row) > 4 else "")
                tag_category = str(row[5] if len(row) > 5 else "")
                if category != "0":
                    continue
                if "禁" in tag_category or "NSFW" in tag_category.upper():
                    continue
                if not tag or tag in canvas_danbooru_policy.QUALITY_TAGS:
                    continue
                if tag in PLAIN_OUTPUT_TAGS:
                    continue
                if canvas_danbooru_policy.is_named_character_leak_tag(tag):
                    continue
                if canvas_danbooru_policy.is_named_character_default_detail_tag(tag):
                    continue
                for key_source in (tag,):
                    key = _semantic_lookup_key(key_source)
                    if key:
                        lookup.setdefault(key, tag)
                aliases = str(row[3] if len(row) > 3 else "")
                for alias in re.split(r"[,|]", aliases):
                    if not _semantic_lookup_term_allowed_for_tag(alias, tag):
                        continue
                    key = _semantic_lookup_key(alias)
                    if key:
                        lookup.setdefault(key, tag)
                for item in re.split(r"[,|/，、；;]", translation):
                    if not _semantic_lookup_term_allowed_for_tag(item, tag):
                        continue
                    key = _semantic_lookup_key(item)
                    if key:
                        lookup.setdefault(key, tag)
    except Exception:
        return {}
    return lookup


def _canonical_semantic_tag(raw):
    clean = _clean_tag(raw)
    clean = canvas_danbooru_policy.REPAIR_TAG_ALIASES.get(clean, clean)
    lookup = _danbooru_general_tag_lookup()
    if clean in lookup.values():
        return clean
    key = _semantic_lookup_key(raw)
    return lookup.get(key, "")


LLM_DRAFT_TAG_MIN = 24
LLM_DRAFT_TAG_MAX = 36
LLM_DRAFT_TAG_SOFT_MIN = 16
LLM_DRAFT_HARD_MAX = 48
LLM_DRAFT_FORBIDDEN_TAGS = {
    "lowres", "bad_id", "bad_pixiv_id", "md5_mismatch",
    "translation_request", "translated", "check_translation",
    "commentary_request", "commentary", "artist_name", "signature",
    "watermark", "sample_watermark", "text", "english_text", "chinese_text",
    "censored", "mosaic_censoring", "bar_censor",
    "prompt", "positive_prompt", "negative_prompt", "negative", "parameters",
    "params", "metadata", "seed", "steps", "cfg", "cfg_scale", "guidance",
    "guidance_scale", "sampler", "scheduler", "width", "height", "resolution",
}
LLM_DRAFT_FORBIDDEN_FRAGMENTS = (
    "artist", "commentary", "request", "watermark", "signature",
    "lowres", "bad_", "error", "negative_prompt", "positive_prompt",
    "cfg_scale", "guidance_scale",
)
LLM_DRAFT_LOCAL_REPAIR_TAGS = {
    "kneeling", "lying", "on_ground", "injury", "torn_clothes",
    "armor", "lightning", "katana",
}
LLM_DRAFT_FUZZY_ACCEPT_SCORE = 0.82


def _llm_draft_positive_prompt_from_structured_text(prompt_text):
    source = str(prompt_text or "").strip()
    if not source or source[0] not in "{[":
        return ""
    try:
        parsed = json.loads(source)
    except Exception:
        parsed = None
    if isinstance(parsed, dict):
        for key in (
            "positive_prompt", "positivePrompt", "positive", "prompt",
            "image_prompt", "recommended_prompt", "final_prompt", "draft_prompt",
            "tags", "danbooru_tags", "positive_tags",
        ):
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, list):
                return ", ".join(str(item).strip() for item in value if str(item).strip())
    elif isinstance(parsed, list):
        return ", ".join(str(item).strip() for item in parsed if str(item).strip())
    match = re.search(
        r'"(?:positive_prompt|positivePrompt|positive|prompt|image_prompt|recommended_prompt|final_prompt|draft_prompt)"\s*:\s*"((?:\\.|[^"\\])*)"',
        source,
        re.I | re.S,
    )
    if match:
        try:
            return str(json.loads(f'"{match.group(1)}"') or "").strip()
        except Exception:
            return str(match.group(1) or "").strip()
    return ""


def _split_llm_draft_tags(prompt_text):
    structured_prompt = _llm_draft_positive_prompt_from_structured_text(prompt_text)
    if structured_prompt:
        prompt_text = structured_prompt
    output = []
    for raw in str(prompt_text or "").split(","):
        text = str(raw or "").strip()
        if not text:
            continue
        if re.match(r"^(?:negative_prompt|negative|parameters|params|metadata|seed|steps|cfg|cfg_scale|width|height|sampler|scheduler)\s*[:=]", text, re.I):
            continue
        if re.match(r"^(?:prompt|positive_prompt|draft_prompt|final_prompt|recommended_prompt|image_prompt)\s*[:=]", text, re.I):
            text = re.sub(r"^(?:prompt|positive_prompt|draft_prompt|final_prompt|recommended_prompt|image_prompt)\s*[:=]\s*", "", text, flags=re.I).strip()
            if not text:
                continue
        weighted = re.fullmatch(r"\(([^:()]+):[0-9.]+\)", text)
        if weighted:
            text = weighted.group(1).strip()
        output.append(text)
    return output


def _llm_draft_clean_tag_or_phrase(value):
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"^\((.*)\)$", r"\1", text).strip()
    text = re.sub(r":[0-9.]+$", "", text).strip()
    clean = _clean_tag(text)
    clean = canvas_danbooru_policy.REPAIR_TAG_ALIASES.get(clean, clean)
    return clean


def _llm_draft_tag_forbidden(clean):
    if not clean:
        return True
    if "_(cosplay)" in clean or clean.endswith("_cosplay"):
        return True
    if clean == "text" or clean.endswith("_text") or clean.startswith("text_"):
        return True
    if clean in LLM_DRAFT_FORBIDDEN_TAGS:
        return True
    if canvas_danbooru_policy.is_named_character_default_detail_tag(clean):
        return True
    if canvas_danbooru_policy.is_forbidden_positive_tag(clean):
        return True
    return any(fragment in clean for fragment in LLM_DRAFT_FORBIDDEN_FRAGMENTS)


def _llm_draft_count_word_to_int(value):
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    mapping = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "\u4e00": 1,
        "\u4e8c": 2,
        "\u4e24": 2,
        "\u5169": 2,
        "\u4fe9": 2,
        "\u5006": 2,
        "\u4e09": 3,
        "\u56db": 4,
        "\u4e94": 5,
        "\u516d": 6,
    }
    return mapping.get(text)


def _llm_draft_explicit_subject_total_count(text):
    source = str(text or "")
    if not source.strip():
        return None
    if re.search(
        r"(?:\u6ca1\u6709|\u6c92\u6709|\u65e0|\u7121|\u4e0d\u8981|\u522b\u753b|\u5225\u756b|no|without).{0,8}(?:\u4eba|\u4eba\u7269|\u89d2\u8272|humans?|people|characters?)",
        source,
        re.I,
    ):
        return 0
    try:
        explicit = _explicit_subject_mention_counts(source)
    except Exception:
        explicit = {}
    explicit_total = int((explicit or {}).get("girls") or 0) + int((explicit or {}).get("boys") or 0)
    if explicit_total > 0:
        return explicit_total
    match = re.search(
        r"(?P<count>\d+|one|two|three|four|five|six|\u4e00|\u4e8c|\u4e24|\u5169|\u4fe9|\u5006|\u4e09|\u56db|\u4e94|\u516d)"
        r"\s*(?:\u4e2a|\u500b|\u4f4d|\u540d)?\s*"
        r"(?:\u4eba|\u4eba\u7269|\u89d2\u8272|people|persons|characters?)",
        source,
        re.I,
    )
    if not match:
        return None
    count = _llm_draft_count_word_to_int(match.group("count"))
    if count is None:
        return None
    return max(0, min(int(count), 12))


def _llm_draft_character_base_key(tag):
    clean = str(tag or "").strip().lower()
    if not clean:
        return ""
    clean = re.sub(r"_\([^)]+\)$", "", clean)
    clean = re.sub(r"\s*\([^)]+\)$", "", clean)
    return clean


def _llm_draft_filter_duplicate_resolved_tags(tags, resolution):
    values = [_clean_tag(tag) for tag in (tags or []) if _clean_tag(tag)]
    if len(values) <= 1:
        return values
    rank_by_tag = {}
    for index, row in enumerate((resolution or {}).get("resolved") or []):
        if not isinstance(row, dict):
            continue
        tag = _clean_tag(row.get("tag"))
        if not tag:
            continue
        source = str(row.get("source") or "").lower()
        glossary = 1 if "character_glossary" in source or row.get("glossary_status") else 0
        priority = float(row.get("_priority") or 0)
        score = float(row.get("score") or 0)
        count = float(row.get("count") or 0)
        rank_by_tag[tag] = (glossary, priority, score, count, -index)
    grouped = {}
    for index, tag in enumerate(values):
        grouped.setdefault(_llm_draft_character_base_key(tag) or tag, []).append((index, tag))
    keep = set()
    for grouped_tags in grouped.values():
        if len(grouped_tags) == 1:
            keep.add(grouped_tags[0][0])
            continue
        keep.add(max(grouped_tags, key=lambda item: rank_by_tag.get(item[1], (0, 0, 0, 0, -item[0])))[0])
    return [tag for index, tag in enumerate(values) if index in keep]


def _llm_draft_expected_identity_context(user_prompt, draft_prompt):
    try:
        resolution = canvas_danbooru_service._canvas_requested_character_resolution(user_prompt, "")
    except Exception:
        resolution = {}
    if not isinstance(resolution, dict) or resolution.get("state") != "resolved":
        return [], [], []
    try:
        resolved, copyright = _expanded_identity_tags(user_prompt, "", resolution)
    except Exception:
        resolved = [
            _clean_tag(row.get("tag"))
            for row in resolution.get("resolved") or []
            if isinstance(row, dict) and row.get("tag")
        ]
        copyright = [
            _clean_tag(row.get("tag"))
            for row in resolution.get("copyright_candidates") or []
            if isinstance(row, dict) and row.get("tag")
        ]
    resolved = _llm_draft_filter_duplicate_resolved_tags(resolved, resolution)
    explicit_total = _llm_draft_explicit_subject_total_count(user_prompt)
    if explicit_total is not None and explicit_total > 0 and len(resolved or []) > explicit_total:
        resolved = list(resolved or [])[:explicit_total]
    try:
        count_tags = _subject_count_tags(user_prompt, "", resolved, "")
    except Exception:
        count_tags = _known_character_subject_count_tags(resolved)
    return list(resolved or []), list(copyright or []), list(count_tags or [])


def _llm_draft_clean_set_has_tag(clean_set, tag):
    clean = _clean_tag(tag)
    if not clean:
        return False
    if clean in clean_set:
        return True
    clean_key = _semantic_lookup_key(clean)
    for item in clean_set or ():
        item_key = _semantic_lookup_key(item)
        if item_key and clean_key and (item_key == clean_key or item_key in clean_key or clean_key in item_key):
            return True
    return False


def _llm_draft_has_defeated_marker(raw_tags, clean_set):
    if set(clean_set or ()).intersection({"defeated", "lying", "on_ground", "kneeling", "injury", "torn_clothes", "battle", "battlefield", "fighting"}):
        return True
    for tag in raw_tags or ():
        text = str(tag or "")
        if _has_defeated_intent(text) or _has_defeated_down_intent(text) or _has_kneeling_intent(text) or _has_battle_damaged_clothing_intent(text):
            return True
    return False


def _llm_draft_preserves_core_user_intent(user_prompt, raw_tags, clean_set):
    source = str(user_prompt or "")
    if _has_defeated_intent(source) and not _llm_draft_has_defeated_marker(raw_tags, clean_set):
        return False
    if _has_group_other_people_intent(source) and not (
        set(clean_set or ()).intersection({"multiple_others", "group", "crowd"})
        or any(re.search(r"\b(?:children|kids|classmates|friends|students)\b", str(tag or ""), re.I) for tag in raw_tags or ())
    ):
        return False
    if _has_kindergarten_scene_intent(source) and not set(clean_set or ()).intersection({"kindergarten", "classroom", "school", "indoors"}):
        return False
    return True


def validate_llm_draft_action(action, user_prompt="", target_requires_danbooru=True):
    issues = []
    if not target_requires_danbooru:
        return {"valid": True, "issues": [], "tag_count": 0, "draft_prompt": ""}
    if not isinstance(action, dict):
        return {"valid": False, "issues": ["missing_action"], "tag_count": 0, "draft_prompt": ""}
    action_name = str(action.get("action") or action.get("type") or "").strip().lower()
    if action_name not in {"generate_image", "text_to_image"}:
        issues.append("action must be generate_image")
    if str(action.get("_salvaged_malformed_json") or "").lower() == "true":
        issues.append("malformed JSON was salvaged")
    has_explicit_draft = bool(str(action.get("draft_prompt") or "").strip())
    draft_prompt = str(action.get("draft_prompt") or action.get("prompt") or action.get("recommended_prompt") or action.get("final_prompt") or "").strip()
    if not has_explicit_draft:
        issues.append("missing explicit draft_prompt field")
    if not draft_prompt:
        issues.append("missing draft_prompt")
        return {"valid": False, "issues": issues, "tag_count": 0, "draft_prompt": ""}
    if "```" in draft_prompt:
        issues.append("draft_prompt contains markdown fence")
    if re.search(r"[\u3400-\u9fff]", draft_prompt):
        issues.append("draft_prompt contains Chinese text")
    if re.search(r"(?:^|,|\s)(?:width|height|resolution|aspect[_\s-]*ratio|seed|steps?|cfg|guidance)(?:\s*[:=]|\b)", draft_prompt, re.I):
        issues.append("draft_prompt contains generation control parameter")
    tags = _split_llm_draft_tags(draft_prompt)
    tag_count = len(tags)
    draft_below_target_count = tag_count < LLM_DRAFT_TAG_MIN
    if tag_count < LLM_DRAFT_TAG_SOFT_MIN:
        issues.append(f"draft_prompt has too few tags ({tag_count}; expected {LLM_DRAFT_TAG_MIN}-{LLM_DRAFT_TAG_MAX})")
    if tag_count > LLM_DRAFT_TAG_MAX:
        issues.append(f"draft_prompt has too many tags ({tag_count}; expected {LLM_DRAFT_TAG_MIN}-{LLM_DRAFT_TAG_MAX})")
    if tag_count > LLM_DRAFT_HARD_MAX:
        issues.append("draft_prompt is far too long")
    cleaned = []
    for tag in tags:
        if len(tag) > 64:
            issues.append(f"tag phrase too long: {tag[:40]}")
        if len(re.findall(r"[a-zA-Z0-9]+", tag)) > 6:
            issues.append(f"tag phrase has too many words: {tag[:40]}")
        if re.search(r"[.!?。！？]$", tag):
            issues.append(f"tag phrase looks like prose: {tag[:40]}")
        clean = _llm_draft_clean_tag_or_phrase(tag)
        if not clean:
            issues.append(f"invalid empty tag phrase: {tag[:40]}")
            continue
        if _llm_draft_tag_forbidden(clean) and not canvas_danbooru_policy.is_named_character_default_detail_tag(clean):
            issues.append(f"forbidden draft tag: {clean}")
        cleaned.append(clean)
    clean_set = set(cleaned)
    multi_count = clean_set.intersection({"2girls", "3girls", "4girls", "5girls", "6girls", "2boys", "3boys", "4boys", "5boys", "6boys", "multiple_others"})
    if "solo" in clean_set and multi_count:
        issues.append("subject conflict: solo with multiple subjects")
    if "no_humans" in clean_set and clean_set.intersection(SUBJECT_COUNT_TAGS - {"no_humans"}):
        issues.append("subject conflict: no_humans with human count tags")
    if {"indoors", "outdoors"}.issubset(clean_set):
        issues.append("scene conflict: indoors and outdoors")
    if re.search(r"\u5c0f\u670b\u53cb|\u5b69\u5b50|\u5b69\u7ae5|\u513f\u7ae5|children|kids|classmates", str(user_prompt or ""), re.I):
        if "solo" in clean_set:
            issues.append("user requested surrounding children/classmates but draft uses solo")
    if _has_passive_external_actor_intent(user_prompt):
        if "solo" in clean_set:
            issues.append("subject conflict: external interaction request uses solo")
        if clean_set.intersection({"1girl", "1boy"}) and not _subject_count_implies_multiple(clean_set):
            issues.append("missing external actor for requested interaction")
    if _has_defeated_intent(user_prompt):
        if not _llm_draft_has_defeated_marker(tags, clean_set):
            issues.append("missing requested defeated state")
        if clean_set.intersection({"standing", "walking"}) and not clean_set.intersection({"lying", "on_ground", "kneeling"}):
            issues.append("subject pose conflicts with requested defeated state")
    if draft_below_target_count and tag_count >= LLM_DRAFT_TAG_SOFT_MIN and not _llm_draft_preserves_core_user_intent(user_prompt, tags, clean_set):
        issues.append(f"draft_prompt has too few tags ({tag_count}; expected {LLM_DRAFT_TAG_MIN}-{LLM_DRAFT_TAG_MAX}) and misses core user intent")
    expected_resolved, _expected_copyright, expected_count_tags = _llm_draft_expected_identity_context(user_prompt, draft_prompt)
    if expected_resolved:
        for tag in expected_resolved:
            if not _llm_draft_clean_set_has_tag(clean_set, tag):
                issues.append(f"missing requested character tag: {tag}")
    if len(expected_resolved or []) > 1:
        if "solo" in clean_set:
            issues.append("subject conflict: solo with requested multiple characters")
        for tag in expected_count_tags or []:
            if tag == "multiple_others":
                continue
            if tag in SUBJECT_COUNT_TAGS and tag not in clean_set:
                issues.append(f"missing expected subject count tag: {tag}")
        expected_multi = set(expected_count_tags or []).intersection({"2girls", "3girls", "4girls", "5girls", "6girls", "2boys", "3boys", "4boys", "5boys", "6boys"})
        if expected_multi and clean_set.intersection({"1girl", "1boy", "solo"}):
            issues.append("subject conflict: single-subject tag with requested multi-character scene")
    return {
        "valid": not issues,
        "issues": list(dict.fromkeys(issues))[:16],
        "tag_count": tag_count,
        "draft_prompt": draft_prompt,
    }


def validate_llm_draft_actions(actions, user_prompt="", target_requires_danbooru=True):
    if not target_requires_danbooru:
        return {"valid": True, "issues": [], "tag_count": 0}
    image_actions = [
        item for item in (actions or [])
        if isinstance(item, dict) and str(item.get("action") or item.get("type") or "").strip().lower() in {"generate_image", "text_to_image"}
    ]
    issues = []
    if len(image_actions) != 1:
        issues.append(f"expected exactly one image action, got {len(image_actions)}")
        return {"valid": False, "issues": issues, "tag_count": 0}
    result = validate_llm_draft_action(image_actions[0], user_prompt=user_prompt, target_requires_danbooru=target_requires_danbooru)
    issues.extend(result.get("issues") or [])
    return {
        "valid": not issues,
        "issues": list(dict.fromkeys(issues))[:16],
        "tag_count": int(result.get("tag_count") or 0),
        "draft_prompt": result.get("draft_prompt") or "",
    }


def _llm_draft_known_general_tags():
    return set(_danbooru_general_tag_lookup().values()).union(
        _curated_tagcart_tag_set(),
        SCENE_TAG_POOL,
        SETTING_TAG_POOL,
        ACTION_TAG_POOL,
        POSE_TAG_POOL,
        ATMOSPHERE_TAG_POOL,
        EXPRESSION_TAG_POOL,
        SOURCE_STYLE_CARRYOVER_TAGS,
    )


@functools.lru_cache(maxsize=1)
def _llm_draft_fuzzy_rows():
    rows = []
    for row in _random_database_ranked_tag_rows(limit=24000):
        tag = _clean_tag((row or {}).get("tag"))
        if not tag or _llm_draft_tag_forbidden(tag):
            continue
        key = _semantic_lookup_key(tag)
        if not key or len(key) < 3:
            continue
        tokens = tuple(token for token in re.split(r"[_/()'!-]+", tag) if len(token) >= 3)
        rows.append({
            "tag": tag,
            "key": key,
            "tokens": tokens,
            "count": int((row or {}).get("count") or 0),
        })
    return tuple(rows)


def _fuzzy_canonical_draft_tag(raw):
    key = _semantic_lookup_key(raw)
    if not key or len(key) < 4:
        return "", 0.0
    raw_tokens = set(token for token in re.findall(r"[a-z0-9]+", str(raw or "").lower()) if len(token) >= 3)
    best = ("", 0.0)
    for row in _llm_draft_fuzzy_rows():
        tag = row.get("tag")
        row_key = row.get("key")
        score = 0.0
        if row_key == key:
            score = 1.0
        elif len(key) >= 5 and (key in row_key or row_key in key):
            score = min(len(key), len(row_key)) / max(len(key), len(row_key))
        elif raw_tokens:
            row_tokens = set(row.get("tokens") or ())
            overlap = len(raw_tokens.intersection(row_tokens))
            if overlap:
                score = overlap / max(len(raw_tokens), len(row_tokens))
        if score < 0.58:
            ratio = SequenceMatcher(None, key, row_key).ratio()
            if ratio >= 0.78:
                score = ratio * 0.9
        if score > best[1]:
            best = (tag, score)
    if best[1] >= 0.62:
        return best
    return "", best[1]


def _llm_draft_identity_match_allowed(raw, identity_tag, user_prompt=""):
    clean_identity = _clean_tag(identity_tag)
    if not clean_identity:
        return False
    raw_clean = _llm_draft_clean_tag_or_phrase(raw)
    raw_key = _semantic_lookup_key(raw)
    identity_key = _semantic_lookup_key(clean_identity)
    if not raw_key or not identity_key:
        return False
    scene_root = ""
    for root in COMMON_SCENE_IDENTITY_ROOT_TAGS:
        root_key = _semantic_lookup_key(root)
        if root_key and (raw_key == root_key or raw_key.startswith(root_key)):
            scene_root = root
            break
    if scene_root and clean_identity.startswith(scene_root + "_("):
        user_key = _semantic_lookup_key(user_prompt)
        return bool(user_key and identity_key in user_key)
    if raw_clean in SCENE_TAG_POOL or raw_clean in SETTING_TAG_POOL or raw_clean in ATMOSPHERE_TAG_POOL:
        return raw_key == identity_key
    return raw_key == identity_key or raw_key in identity_key or identity_key in raw_key


def _canonicalize_llm_draft_single_tag(raw, adult=False):
    raw_text = str(raw or "").strip()
    clean = _llm_draft_clean_tag_or_phrase(raw_text)
    if not clean:
        return [], "blocked", 0.0
    if _llm_draft_tag_forbidden(clean) and not (
        _has_defeated_intent(raw_text)
        or _has_defeated_down_intent(raw_text)
        or _has_kneeling_intent(raw_text)
        or _has_battle_damaged_clothing_intent(raw_text)
    ):
        return [], "blocked", 0.0
    if clean in SUBJECT_COUNT_TAGS or clean in {"solo"}:
        return [clean], "protected", 1.0
    if clean in canvas_danbooru_policy.QUALITY_TAGS or clean in PLAIN_OUTPUT_TAGS:
        return [clean], "protected", 1.0
    if adult and re.search(RANDOM_ADULT_MINOR_RISK_PATTERN, clean):
        return [], "blocked_minor_risk", 0.0
    repaired = canvas_danbooru_policy.REPAIR_TAG_ALIASES.get(clean)
    if repaired and not _llm_draft_tag_forbidden(repaired):
        return [repaired], "repair_alias", 0.98
    known = _llm_draft_known_general_tags()
    if clean in known and _canonical_tag_allowed(clean):
        return [clean], "exact", 1.0
    semantic = _canonical_semantic_tag(raw_text)
    if semantic and not _llm_draft_tag_forbidden(semantic) and _canonical_tag_allowed(semantic):
        return [semantic], "semantic_lookup", 0.94
    phrase_tags = []
    phrase = raw_text.lower().replace("_", " ")
    if _has_defeated_intent(phrase):
        _append_unique(phrase_tags, _defeated_state_tags_for_text(phrase))
    if _has_kneeling_intent(phrase):
        _append_unique(phrase_tags, ["kneeling", "on_ground"])
    if _has_battle_damaged_clothing_intent(phrase):
        _append_unique(phrase_tags, ["torn_clothes"])
    if re.search(r"\b(?:armor|armour)\b|\u76d4\u7532|\u94e0\u7532|\u93a7\u7532", phrase, re.I):
        _append_unique(phrase_tags, ["armor"])
    if re.search(r"\b(?:lightning|electric(?:ity)?|thunder)\b|\u95ea\u7535|\u9583\u96fb|\u96f7\u7535|\u96f7\u96fb", phrase, re.I):
        _append_unique(phrase_tags, ["lightning"])
    if re.search(r"\bkatana\b|\u5200|\u592a\u5200", phrase, re.I):
        _append_unique(phrase_tags, ["katana"])
    if re.search(r"\b(?:children|kids|classmates|friends)\b|\u5c0f\u670b\u53cb|\u5b69\u5b50|\u5b69\u7ae5|\u540c\u5b66", phrase, re.I):
        _append_unique(phrase_tags, ["multiple_others"])
    if re.search(r"\bplay(?:ing)?\b|\u73a9|\u73a9\u800d|\u6e38\u620f", phrase, re.I):
        _append_unique(phrase_tags, ["playing"])
    if re.search(r"\bkindergarten|preschool\b|\u5e7c\u513f\u56ed|\u5e7c\u5152\u5712", phrase, re.I):
        _append_unique(phrase_tags, ["kindergarten", "classroom", "school", "indoors"])
    if re.search(r"\bclassroom\b|\u6559\u5ba4", phrase, re.I):
        _append_unique(phrase_tags, ["classroom", "school", "indoors"])
    if phrase_tags:
        phrase_tags = [
            tag for tag in phrase_tags
            if tag in SUBJECT_COUNT_TAGS
            or tag in LLM_DRAFT_LOCAL_REPAIR_TAGS
            or (not _llm_draft_tag_forbidden(tag) and _canonical_tag_allowed(tag))
        ]
        if phrase_tags:
            return phrase_tags, "phrase_hint", 0.86
    if re.search(r"\([^)]+\)|\b(?:genshin|honkai|blue\s+archive|fate|pokemon|azur\s+lane|arknights|umamusume)\b", raw_text, re.I):
        return [], "unmatched_identity_like", 0.0
    fuzzy, score = _fuzzy_canonical_draft_tag(raw_text)
    if (
        fuzzy
        and float(score or 0.0) >= LLM_DRAFT_FUZZY_ACCEPT_SCORE
        and not _llm_draft_tag_forbidden(fuzzy)
        and _canonical_tag_allowed(fuzzy)
    ):
        return [fuzzy], "fuzzy_db", score
    if fuzzy:
        return [], "fuzzy_low_confidence", score
    return [], "unmatched", score


def canonicalize_llm_draft_tags(prompt_or_tags, user_prompt="", source_prompt="", resolved_tags=None, copyright_tags=None, prompt_intent=None, adult=False, limit=64):
    raw_tags = prompt_or_tags
    if isinstance(prompt_or_tags, str):
        raw_tags = _split_llm_draft_tags(prompt_or_tags)
    output = []
    mappings = []
    unmatched = []
    subject_count_tags = []
    structured = normalize_structured_prompt_intent(prompt_intent)
    _append_unique(output, structured.get("locked_tags") or [])
    resolved = _filter_unrequested_common_scene_identity_tags(resolved_tags or [], user_prompt=user_prompt)
    copyright = _filter_unrequested_common_scene_identity_tags(copyright_tags or [], user_prompt=user_prompt)
    for tag in raw_tags or []:
        raw_key = _semantic_lookup_key(tag)
        identity_match = []
        for identity_tag in resolved + copyright:
            identity_key = _semantic_lookup_key(identity_tag)
            if (
                raw_key
                and identity_key
                and _llm_draft_identity_match_allowed(tag, identity_tag, user_prompt=user_prompt)
            ):
                identity_match.append(identity_tag)
        if identity_match:
            mapped, source, score = identity_match[:2], "resolved_identity", 1.0
        else:
            mapped, source, score = _canonicalize_llm_draft_single_tag(tag, adult=adult)
        if not mapped:
            unmatched.append(str(tag or "").strip())
        else:
            _append_unique(output, mapped)
            for item in mapped:
                if item in SUBJECT_COUNT_TAGS or item == "solo":
                    _append_unique(subject_count_tags, [item])
        mappings.append({
            "raw": str(tag or "").strip(),
            "tags": mapped,
            "source": source,
            "score": round(float(score or 0.0), 3),
        })
    if resolved:
        _append_unique(output, resolved)
    if copyright:
        _append_unique(output, copyright)
    if subject_count_tags:
        output = [tag for tag in output if tag != "solo" or not set(subject_count_tags).intersection(SUBJECT_COUNT_TAGS - {"no_humans"})]
    user_intent = plan_prompt_intent(user_prompt, "", resolution=None)
    _append_unique(output, user_intent.get("composition_tags") or [])
    _append_unique(output, user_intent.get("scene_tags") or [])
    intent = plan_prompt_intent(user_prompt, source_prompt or ", ".join(output), resolution=None)
    output = _apply_user_explicit_conflict_filters(output, intent)
    output = _apply_indoor_scene_conflict_filters(output, intent)
    output = _apply_bathing_scene_conflict_filters(output, intent)
    output = _apply_bed_scene_conflict_filters(output, intent)
    output = _apply_beach_scene_conflict_filters(output, intent)
    output = _apply_street_scene_conflict_filters(output, intent)
    output = _apply_major_scene_conflict_filters(output, intent)
    output = _apply_explicit_visual_bias_filters(output, user_prompt, source_prompt)
    output = _sanitize_final_canonical_tags(
        output,
        user_prompt,
        source_prompt=source_prompt,
        resolved_tags=resolved,
        copyright_tags=copyright,
        intent=intent,
        subject_count_tags=subject_count_tags,
    )
    max_limit = max(1, min(int(limit or 64), 96))
    output = output[:max_limit]
    return {
        "tags": output,
        "prompt": _prompt_text_from_tags(output, user_prompt, source_prompt=source_prompt, resolved_tags=resolved, copyright_tags=copyright, variation_strength="off"),
        "unmatched_hints": [item for item in unmatched if item][:24],
        "mappings": mappings[:80],
        "tag_count": len(output),
        "canonicalize_source": "llm_draft_db_canonicalize",
        "intent_hints": [item for item in unmatched if item][:12],
    }


def _semantic_tag_allowed(tag):
    clean = _clean_tag(tag)
    if not clean or clean in canvas_danbooru_policy.QUALITY_TAGS:
        return False
    if clean in PLAIN_OUTPUT_TAGS:
        return False
    if canvas_danbooru_policy.is_named_character_leak_tag(clean):
        return False
    if canvas_danbooru_policy.is_named_character_default_detail_tag(clean):
        return False
    return clean in SCENE_TAG_POOL or clean in _curated_tagcart_tag_set() or clean in set(_danbooru_general_tag_lookup().values())


def _looks_like_compact_tag_prompt(text):
    source = str(text or "").strip()
    if not source or re.search(r"[\u3400-\u9fff]", source) or source.count(",") < 2:
        return False
    parts = [part.strip() for part in source.split(",") if part.strip()]
    if len(parts) < 3:
        return False
    tagish = 0
    for part in parts:
        clean = part.strip().strip("()")
        clean = re.sub(r":[0-9.]+$", "", clean).strip()
        if re.fullmatch(r"[a-z0-9_:/.'() -]+", clean, re.I):
            tagish += 1
    return tagish / max(1, len(parts)) >= 0.8


def _semantic_candidate_tags(user_prompt, source_prompt=""):
    output = []
    user_text = str(user_prompt or "")
    source_text = str(source_prompt or "")
    combined = "\n".join(item for item in (user_text, source_text) if item)
    rule_text = user_text if _looks_like_compact_tag_prompt(source_text) else combined
    _append_unique(output, _rule_tags(rule_text, SEMANTIC_SCENE_RULES))

    # Let the LLM suggest loose action/scene words, then canonicalize them through the local Danbooru DB.
    for raw in re.split(r"[,，\n;；]+", combined):
        raw = raw.strip()
        if not raw or len(raw) > 64:
            continue
        if re.search(r"[\u3400-\u9fff]", raw) and len(raw) > 3:
            continue
        # Exact snake_case tags from a stale model prompt are handled as low-priority source tags.
        # This semantic layer is only for natural-language phrases and aliases.
        if re.fullmatch(r"[a-z0-9_()']+", raw):
            continue
        tag = _canonical_semantic_tag(raw)
        if tag and _semantic_tag_allowed(tag):
            _append_unique(output, [tag])

    return [tag for tag in output if _semantic_tag_allowed(tag)]


def _adult_level1_suggestive_candidate_tags(user_prompt, source_prompt=""):
    combined = "\n".join(item for item in (str(user_prompt or ""), str(source_prompt or "")) if item)
    output = []
    for tag in _rule_tags(combined, ADULT_LEVEL1_SUGGESTIVE_RULES):
        if tag in ADULT_LEVEL1_SUGGESTIVE_TAGS:
            _append_unique(output, [tag])
    for raw in re.split(r"[,，\n;；]+", combined):
        raw = raw.strip()
        if not raw or len(raw) > 64:
            continue
        clean = _clean_tag(raw)
        clean = canvas_danbooru_policy.REPAIR_TAG_ALIASES.get(clean, clean)
        clean = ADULT_LEVEL1_SUGGESTIVE_ALIASES.get(clean, clean)
        if clean in ADULT_LEVEL1_SUGGESTIVE_TAGS:
            _append_unique(output, [clean])
    return [tag for tag in output if _adult_level1_suggestive_tag_allowed(tag)]


def _adult_level1_suggestive_tag_allowed(tag):
    clean = _clean_tag(tag)
    return bool(clean and clean in ADULT_LEVEL1_SUGGESTIVE_TAGS and not canvas_danbooru_policy.is_named_character_leak_tag(clean))


def _adult_phrase_trigger_map_path():
    root = getattr(canvas_danbooru_service, "_CANVAS_DANBOORU_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, "docs", "adult_phrase_trigger_map.csv")


@functools.lru_cache(maxsize=1)
def _adult_phrase_trigger_rows():
    rows = []
    path = _adult_phrase_trigger_map_path()
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                phrase = str(row.get("phrase") or "").strip()
                tag = _clean_tag(row.get("canonical_tag"))
                if not phrase or not tag:
                    continue
                try:
                    level = max(1, min(3, int(float(str(row.get("level") or "1").strip()))))
                except Exception:
                    level = 1
                rows.append({
                    "phrase": phrase,
                    "tag": canvas_danbooru_policy.REPAIR_TAG_ALIASES.get(tag, tag),
                    "level": level,
                    "note": str(row.get("note") or "").strip(),
                })
    except Exception:
        return ()
    rows.sort(key=lambda item: (-len(item.get("phrase") or ""), item.get("phrase") or ""))
    return tuple(rows)


@functools.lru_cache(maxsize=1)
def _adult_phrase_trigger_level_lookup():
    lookup = {}
    for row in _adult_phrase_trigger_rows():
        tag = _clean_tag(row.get("tag"))
        if not tag:
            continue
        level = max(1, min(3, int(row.get("level") or 1)))
        current = lookup.get(tag)
        lookup[tag] = level if current is None else min(current, level)
    return lookup


def _adult_phrase_tag_level(tag):
    return _adult_phrase_trigger_level_lookup().get(_clean_tag(tag))


def _adult_phrase_candidate_tags(user_prompt, source_prompt=""):
    combined = "\n".join(item for item in (str(user_prompt or ""), str(source_prompt or "")) if item)
    combined_lower = combined.lower()
    output = []
    matched_phrases = []
    for row in _adult_phrase_trigger_rows():
        phrase = row.get("phrase") or ""
        tag = _clean_tag(row.get("tag"))
        if not phrase or not tag:
            continue
        if any(phrase != previous and phrase in previous for previous in matched_phrases):
            continue
        if canvas_danbooru_policy.is_named_character_leak_tag(tag):
            continue
        if _phrase_term_matches(combined_lower, phrase):
            matched_phrases.append(phrase)
            _append_unique(output, [tag])
    return output


def _adult_candidate_tags(user_prompt, source_prompt=""):
    if _adult_intent_explicitly_negated(user_prompt):
        return []
    allowlist, lookup, phrase_terms = _adult_tagcart_allowlist_data()
    combined = "\n".join(item for item in (str(user_prompt or ""), str(source_prompt or "")) if item)
    combined_lower = combined.lower()
    output = []
    _append_unique(output, _adult_phrase_candidate_tags(user_prompt, source_prompt))
    if allowlist:
        for term, tag in phrase_terms:
            if term and _phrase_term_matches(combined_lower, term) and tag in allowlist:
                _append_unique(output, [tag])

        # Keep code rules as a compatibility fallback; local NSFW aliases are the primary trigger source.
        for tag in _rule_tags(combined, ADULT_INTENT_RULES):
            if tag in allowlist:
                _append_unique(output, [tag])

        for raw in re.split(r"[,，\n;；]+", combined):
            raw = raw.strip()
            if not raw or len(raw) > 64:
                continue
            clean = _clean_tag(raw)
            clean = canvas_danbooru_policy.REPAIR_TAG_ALIASES.get(clean, clean)
            if clean in allowlist:
                _append_unique(output, [clean])
                continue
            key = _semantic_lookup_key(raw)
            tag = lookup.get(key)
            if tag in allowlist:
                _append_unique(output, [tag])

    _append_unique(output, _adult_level1_suggestive_candidate_tags(user_prompt, source_prompt))

    return output


def _adult_intent_explicitly_negated(text):
    source = str(text or "")
    if not source:
        return False
    return bool(re.search(
        r"(?:\u4e0d\u662f|\u5e76\u975e|\u975e|\u4e0d\u8981|\u907f\u514d|not|without).{0,10}(?:\u9732\u9aa8|\u8272\u60c5|\u60c5\u8272|\u6027\u573a\u666f|\u6027\u5834\u666f|\u6027\u7231|\u6027\u611b|\u6027\u4ea4|\bnude\b|\bsex\b|\bnsfw\b|\bporn)",
        source,
        re.I,
    ))


def _phrase_term_matches(source, term):
    source = str(source or "")
    term = str(term or "").lower()
    if not source or not term:
        return False
    if re.search(r"[\u3400-\u9fff]", term):
        if term in {"色图", "色圖"} and re.search(rf"角色{re.escape(term[-1])}", source):
            return False
        if term in {"姿势", "姿勢"}:
            return bool(re.search(r"(?:性爱|性愛|性交|性|体位|體位).{0,4}" + re.escape(term), source))
        return term in source
    return bool(re.search(rf"(?<![a-z0-9_]){re.escape(term)}(?![a-z0-9_])", source, re.I))


def detect_adult_intent(user_prompt, source_prompt=""):
    tags = _adult_candidate_tags(user_prompt, source_prompt)
    phrase_tags = set(_adult_phrase_candidate_tags(user_prompt, source_prompt))
    sources = ["tags/weilin_tagcart.csv:NSFW"]
    if phrase_tags.intersection(tags or ()):
        sources.append("docs/adult_phrase_trigger_map.csv")
    if set(tags or ()).intersection(ADULT_LEVEL1_SUGGESTIVE_TAGS):
        sources.append("level1_suggestive_hints")
    elif any((_adult_phrase_tag_level(tag) or 0) <= 1 for tag in tags or () if tag in phrase_tags):
        sources.append("level1_phrase_hints")
    return {
        "is_adult": bool(tags),
        "tags": tags,
        "allowlist_source": "+".join(sources),
    }


def _adult_intent_level(adult_tags, user_prompt="", source_prompt=""):
    tag_set = set(adult_tags or [])
    combined = "\n".join(item for item in (str(user_prompt or ""), str(source_prompt or "")) if item).lower()
    if tag_set.intersection(ADULT_LEVEL3_TAGS) or re.search(r"\u6027\u4ea4|\u505a\u7231|\u505a\u611b|\u63d2\u5165|\u53e3\u4ea4|\u4e73\u4ea4|\u809b\u4ea4|\u6388\u7cbe\u4f53\u4f4d|\u6388\u7cbe\u9ad4\u4f4d|\u4ea4\u914d\u6309\u538b|\bsex\b|penetrat|fellatio|handjob|paizuri|doggystyle|missionary|cowgirl|mating[_\s-]*press", combined, re.I):
        return 3
    if tag_set.intersection(ADULT_LEVEL2_TAGS) or re.search(r"\u6478\u80f8|\u6293\u80f8|\u6478\u5c41|\u6293\u5c41|breast\s*grab|ass\s*grab|topless|nipples", combined, re.I):
        return 2
    return 1


def _adult_intent_is_level1_suggestive_only(adult_tags):
    tag_set = set(adult_tags or [])
    return bool(tag_set) and all(
        tag in ADULT_LEVEL1_SUGGESTIVE_TAGS or (_adult_phrase_tag_level(tag) or 99) <= 1
        for tag in tag_set
    )


def _adult_expression_tag_allowed(tag, level=1):
    clean = _clean_tag(tag)
    level = max(1, min(3, int(level or 1)))
    if clean not in ADULT_EXPRESSION_TAG_ALLOWLIST:
        return False
    if level <= 1 and clean in ADULT_EXPRESSION_LEVEL2_ONLY.union(ADULT_EXPRESSION_LEVEL3_ONLY):
        return False
    if level <= 2 and clean in ADULT_EXPRESSION_LEVEL3_ONLY:
        return False
    return True


def _adult_expression_fallback_tags(level=1):
    level = max(1, min(3, int(level or 1)))
    output = list(ADULT_EXPRESSION_SOFT_TAGS)
    if level >= 2:
        output.extend(ADULT_EXPRESSION_MEDIUM_TAGS)
    if level >= 3:
        output.extend(ADULT_EXPRESSION_EXPLICIT_TAGS)
    return tuple(dict.fromkeys(output))


def _adult_pool_tag_allowed(tag, level=1):
    clean = _clean_tag(tag)
    level = max(1, min(3, int(level or 1)))
    if not clean or clean in canvas_danbooru_policy.QUALITY_TAGS or clean in PLAIN_OUTPUT_TAGS:
        return False
    if len(clean) > 36 or clean.count("_") > 4 or not re.fullmatch(r"[a-z0-9_()'/-]+", clean):
        return False
    if canvas_danbooru_policy.is_named_character_leak_tag(clean):
        return False
    if _adult_expression_tag_allowed(clean, level=level):
        return True
    if any(fragment in clean for fragment in ADULT_POOL_FORBIDDEN_FRAGMENTS):
        return False
    if level <= 1 and any(fragment in clean for fragment in ("nipple", "breast", "suck", "feeding", "fondling", "grab", "lick")):
        return False
    if level < 3 and (
        clean in ADULT_LEVEL3_BLOCKED_FOR_LEVEL1
        or any(fragment in clean for fragment in ADULT_LEVEL3_BLOCKED_FRAGMENTS)
    ):
        return False
    if level <= 1 and clean in ADULT_LEVEL2_TAGS:
        return False
    return True


@functools.lru_cache(maxsize=1)
def _adult_frequency_pool_rows():
    rows = []
    root = getattr(canvas_danbooru_service, "_CANVAS_DANBOORU_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(root, "tags", "weilin_tagcart.csv")
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            for raw in csv.reader(handle):
                if not raw:
                    continue
                group = " ".join(str(raw[index] if len(raw) > index else "") for index in (5, 6, 7))
                if "NSFW" not in group.upper():
                    continue
                try:
                    count = int(str(raw[2] if len(raw) > 2 else 0).strip() or 0)
                except Exception:
                    count = 0
                for tag in _tagcart_tag_candidates(raw[0]):
                    rows.append({"tag": tag, "count": count, "group": group, "source": "weilin_tagcart.csv:NSFW"})
    except Exception:
        pass
    best = {}
    for row in rows:
        tag = _clean_tag(row.get("tag"))
        if not tag:
            continue
        current = best.get(tag)
        if current is None or int(row.get("count") or 0) > int(current.get("count") or 0):
            best[tag] = dict(row, tag=tag)
    return tuple(sorted(best.values(), key=lambda item: int(item.get("count") or 0), reverse=True))


def _safe_float(value, default=0.0):
    try:
        return float(str(value or "").strip())
    except Exception:
        return default


def _safe_int(value, default=0):
    try:
        return int(float(str(value or "").strip()))
    except Exception:
        return default


ADULT_ASSOCIATION_SLOT_MAP = {
    "scene": "setting",
    "camera": "camera",
    "pose_action": "pose",
    "expression": "expression",
    "clothing": "clothing",
    "body_detail": "body",
    "prop": "prop",
    "style_light": "atmosphere",
}

ADULT_ASSOCIATION_EXPLICIT_HINTS = (
    "sex", "vaginal", "anal", "oral", "fellatio", "deepthroat",
    "penetration", "handjob", "footjob", "paizuri", "irrumatio",
    "cunnilingus", "masturbation", "orgasm", "cumshot",
)

ADULT_ASSOCIATION_CONTACT_HINTS = (
    "grab", "touch", "fondling", "kiss", "lick", "suck", "breast_press",
)

ADULT_ASSOCIATION_NEGATIVE_MIN_SCORE = 1000.0
ADULT_ASSOCIATION_NEGATIVE_MAX_LIFT = 0.45
ADULT_FINAL_NEGATIVE_MIN_SCORE = 2500.0
ADULT_FINAL_NEGATIVE_MAX_LIFT = 0.45


def _adult_association_slot_path():
    root = getattr(canvas_danbooru_service, "_CANVAS_DANBOORU_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, "docs", "adult_trigger_slots.csv")


def _adult_negative_conflict_path():
    root = getattr(canvas_danbooru_service, "_CANVAS_DANBOORU_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, "docs", "adult_negative_conflicts.csv")


@functools.lru_cache(maxsize=1)
def _adult_association_slot_rows():
    path = _adult_association_slot_path()
    rows = []
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                trigger = _clean_tag(row.get("trigger_tag"))
                related = _clean_tag(row.get("related_tag"))
                slot = str(row.get("slot") or "").strip()
                if not trigger or not related or slot not in ADULT_ASSOCIATION_SLOT_MAP:
                    continue
                rows.append({
                    "trigger": trigger,
                    "related": related,
                    "slot": slot,
                    "support": _safe_int(row.get("support")),
                    "confidence": _safe_float(row.get("confidence")),
                    "lift": _safe_float(row.get("lift")),
                    "score": _safe_float(row.get("score")),
                    "safety_bin": str(row.get("safety_bin") or "").strip(),
                    "safety_class": str(row.get("safety_class") or "").strip(),
                })
    except Exception:
        return ()
    rows.sort(key=lambda item: (-float(item.get("score") or 0.0), -int(item.get("support") or 0), item.get("trigger") or "", item.get("related") or ""))
    return tuple(rows)


@functools.lru_cache(maxsize=1)
def _adult_association_trigger_set():
    return frozenset(row.get("trigger") for row in _adult_association_slot_rows() if row.get("trigger"))


@functools.lru_cache(maxsize=1)
def _adult_negative_conflict_rows():
    path = _adult_negative_conflict_path()
    rows = []
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                trigger = _clean_tag(row.get("trigger_tag"))
                related = _clean_tag(row.get("related_tag"))
                if not trigger or not related or trigger == related:
                    continue
                rows.append({
                    "trigger": trigger,
                    "related": related,
                    "slot": str(row.get("slot") or "").strip(),
                    "support": _safe_int(row.get("support")),
                    "expected_support": _safe_float(row.get("expected_support")),
                    "lift": _safe_float(row.get("lift"), 1.0),
                    "negative_score": _safe_float(row.get("negative_score")),
                    "safety_bin": str(row.get("safety_bin") or "").strip(),
                    "safety_class": str(row.get("safety_class") or "").strip(),
                    "related_group": str(row.get("related_group") or "").strip(),
                    "related_subgroup": str(row.get("related_subgroup") or "").strip(),
                })
    except Exception:
        return ()
    rows.sort(key=lambda item: (-float(item.get("negative_score") or 0.0), item.get("trigger") or "", item.get("related") or ""))
    return tuple(rows)


@functools.lru_cache(maxsize=1)
def _adult_negative_conflict_lookup():
    lookup = {}
    for row in _adult_negative_conflict_rows():
        trigger = row.get("trigger")
        related = row.get("related")
        if not trigger or not related:
            continue
        current = lookup.setdefault(trigger, {}).get(related)
        if current is None or float(row.get("negative_score") or 0.0) > float(current.get("negative_score") or 0.0):
            lookup.setdefault(trigger, {})[related] = row
    return lookup


def _adult_negative_conflict_row(left, right):
    left = _clean_tag(left)
    right = _clean_tag(right)
    if not left or not right or left == right:
        return None
    lookup = _adult_negative_conflict_lookup()
    return (lookup.get(left) or {}).get(right) or (lookup.get(right) or {}).get(left)


def _adult_negative_pair_is_strong(
    left,
    right,
    min_score=ADULT_ASSOCIATION_NEGATIVE_MIN_SCORE,
    max_lift=ADULT_ASSOCIATION_NEGATIVE_MAX_LIFT,
):
    row = _adult_negative_conflict_row(left, right)
    if not row:
        return False
    return (
        float(row.get("negative_score") or 0.0) >= float(min_score or 0.0)
        and float(row.get("lift") or 1.0) <= float(max_lift or 1.0)
    )


def _adult_negative_conflicts_with_any(
    tag,
    anchors,
    min_score=ADULT_ASSOCIATION_NEGATIVE_MIN_SCORE,
    max_lift=ADULT_ASSOCIATION_NEGATIVE_MAX_LIFT,
):
    clean = _clean_tag(tag)
    for anchor in anchors or ():
        anchor = _clean_tag(anchor)
        if anchor and anchor != clean and _adult_negative_pair_is_strong(anchor, clean, min_score=min_score, max_lift=max_lift):
            return True
    return False


def _adult_association_internal_slot(source_slot, tag):
    slot = ADULT_ASSOCIATION_SLOT_MAP.get(str(source_slot or "").strip())
    clean = _clean_tag(tag)
    if slot == "pose":
        if any(fragment in clean for fragment in ADULT_ASSOCIATION_EXPLICIT_HINTS):
            return "explicit_act"
        if any(fragment in clean for fragment in ADULT_ASSOCIATION_CONTACT_HINTS):
            return "contact"
    return slot


def _adult_prompt_trigger_tags(adult_tags, user_prompt="", source_prompt=""):
    triggers = set(_adult_association_trigger_set())
    if not triggers:
        return []
    output = []
    for tag in adult_tags or ():
        clean = _clean_tag(tag)
        if clean in triggers:
            _append_unique(output, [clean])
    combined = "\n".join(item for item in (str(user_prompt or ""), str(source_prompt or "")) if item)
    for raw in re.split(r"[,，\n;；]+", combined):
        clean = _clean_tag(raw)
        clean = canvas_danbooru_policy.REPAIR_TAG_ALIASES.get(clean, clean)
        if clean in triggers:
            _append_unique(output, [clean])
            continue
        clean = ADULT_LEVEL1_SUGGESTIVE_ALIASES.get(clean, clean)
        if clean in triggers:
            _append_unique(output, [clean])
    combined_lookup = _semantic_lookup_key(combined)
    if combined_lookup:
        for trigger in triggers:
            if trigger in output:
                continue
            term = _semantic_lookup_key(trigger)
            if term and re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", combined_lookup):
                _append_unique(output, [trigger])
    return output


def _adult_association_slot_candidates(adult_tags, user_prompt, source_prompt, level=1, limit_per_slot=20):
    level = max(1, min(3, int(level or 1)))
    matched_triggers = set(_adult_prompt_trigger_tags(adult_tags, user_prompt, source_prompt))
    if not matched_triggers:
        return {}
    slots = {key: [] for key in ADULT_SLOT_HINTS}
    for row in _adult_association_slot_rows():
        if row.get("trigger") not in matched_triggers:
            continue
        tag = _clean_tag(row.get("related"))
        if not _adult_pool_tag_allowed(tag, level=level):
            continue
        if _adult_negative_conflicts_with_any(tag, matched_triggers):
            continue
        slot = _adult_association_internal_slot(row.get("slot"), tag)
        if not slot or slot not in slots:
            continue
        if slot == "explicit_act" and level < 3:
            continue
        if slot == "contact" and level < 2 and tag not in {"kiss"}:
            continue
        if slot == "expression" and not _adult_expression_tag_allowed(tag, level=level):
            continue
        if len(slots[slot]) >= limit_per_slot:
            continue
        _append_unique(slots[slot], [tag])
    return {slot: tuple(tags[:limit_per_slot]) for slot, tags in slots.items() if tags}


def _adult_frequency_slot_candidates(level=1, limit_per_slot=20, adult_tags=None, user_prompt="", source_prompt=""):
    level = max(1, min(3, int(level or 1)))
    slots = {key: [] for key in ADULT_SLOT_HINTS}
    association_slots = _adult_association_slot_candidates(
        adult_tags or (),
        user_prompt,
        source_prompt,
        level=level,
        limit_per_slot=limit_per_slot,
    )
    for slot, tags in association_slots.items():
        _append_unique(slots.setdefault(slot, []), tags)
    for row in _adult_frequency_pool_rows():
        tag = str(row.get("tag") or "")
        if not _adult_pool_tag_allowed(tag, level=level):
            continue
        for slot, hints in ADULT_SLOT_HINTS.items():
            if len(slots[slot]) >= limit_per_slot:
                continue
            if slot == "explicit_act" and level < 3:
                continue
            if slot == "contact" and level < 2 and tag not in {"kiss"}:
                continue
            if slot == "expression" and not _adult_expression_tag_allowed(tag, level=level):
                continue
            if _tag_matches_hints(tag, hints):
                _append_unique(slots[slot], [tag])
    for tag in _adult_expression_fallback_tags(level):
        if len(slots.setdefault("expression", [])) >= limit_per_slot:
            break
        if _adult_pool_tag_allowed(tag, level=level):
            _append_unique(slots["expression"], [tag])
    for slot, tags in ADULT_SAFE_FALLBACK_SLOTS.items():
        if slot == "expression":
            continue
        for tag in tags:
            if len(slots.setdefault(slot, [])) >= limit_per_slot:
                break
            if _adult_pool_tag_allowed(tag, level=level):
                _append_unique(slots[slot], [tag])
    return {slot: tuple(tags[:limit_per_slot]) for slot, tags in slots.items()}


def _adult_variant_tags(adult_intent, user_prompt, source_prompt, current_tags, variation_strength="balanced", variant_seed=None):
    adult_tags = list((adult_intent or {}).get("tags") or [])
    level = _adult_intent_level(adult_tags, user_prompt, source_prompt)
    suggestive_only = _adult_intent_is_level1_suggestive_only(adult_tags)
    strength = max(1, _variation_strength_value(variation_strength, {"scene_branch": "adult"}))
    max_total = {1: 3, 2: 5, 3: 7}.get(strength, 5)
    slots_by_level = {
        1: ("setting", "camera", "clothing", "atmosphere", "expression", "body"),
        2: ("setting", "camera", "clothing", "atmosphere", "expression", "body", "contact", "pose", "prop"),
        3: ("setting", "camera", "clothing", "atmosphere", "expression", "body", "contact", "pose", "explicit_act", "prop"),
    }
    if suggestive_only:
        slots_by_level = dict(slots_by_level)
        slots_by_level[1] = ("setting", "camera", "clothing", "atmosphere", "expression")
    if "nude" in set(adult_tags or ()):
        slots_by_level = {
            key: tuple(slot for slot in values if slot != "clothing")
            for key, values in slots_by_level.items()
        }
    candidates = _adult_frequency_slot_candidates(
        level=level,
        adult_tags=adult_tags,
        user_prompt=user_prompt,
        source_prompt=source_prompt,
    )
    seed_text = json.dumps({
        "adult_tags": adult_tags,
        "current_tags": list(current_tags or []),
        "level": level,
        "source_prompt": source_prompt,
        "user_prompt": user_prompt,
        "variant_seed": variant_seed,
    }, ensure_ascii=False, sort_keys=True)
    output = []
    for slot in slots_by_level[level]:
        if len(output) >= max_total:
            break
        pool = [tag for tag in candidates.get(slot, ()) if tag not in set(current_tags or []) and tag not in set(output)]
        if slot == "expression" and level == 3:
            explicit_pool = [tag for tag in pool if tag in ADULT_EXPRESSION_LEVEL3_ONLY]
            if explicit_pool:
                pool = explicit_pool
        elif slot == "expression" and level == 2:
            medium_pool = [tag for tag in pool if tag in ADULT_EXPRESSION_LEVEL2_ONLY]
            if medium_pool:
                pool = medium_pool
        if not pool:
            continue
        picked = _stable_pick(pool, seed_text + "\n" + slot, 1)
        for tag in picked:
            if _adult_pool_tag_allowed(tag, level=level):
                _append_unique(output, [tag])
    return output[:max_total]


def _adult_named_core_request_only(user_prompt, resolution, adult_tags):
    if not adult_tags:
        return False
    scene_text = _adult_identity_masked_text(user_prompt)
    scene_text = _character_name_masked_text(scene_text, resolution)
    if not str(scene_text or "").strip():
        return True
    if _rule_tags(scene_text, ADULT_SCENE_RULES):
        return False
    if _rule_tags(scene_text, SCENE_RULES):
        return False
    if _semantic_candidate_tags(scene_text, ""):
        return False
    return True


def _adult_focused_context_tags(adult_tags):
    tag_set = set(adult_tags or ())
    if tag_set.intersection(ADULT_ORAL_FOCUS_TAGS) or tag_set.intersection(ADULT_FACE_CUM_FOCUS_TAGS):
        return ["face_focus"]
    if tag_set.intersection(ADULT_SPECIFIC_POSITION_TAGS):
        return ["face_focus"]
    return list(ADULT_CONTEXT_TAGS)


def _adult_focused_support_tags(adult_tags):
    tag_set = set(adult_tags or ())
    output = []
    if tag_set.intersection(ADULT_ORAL_FOCUS_TAGS):
        _append_unique(output, ["tongue_out", "saliva"])
    if "mating_press" in tag_set:
        _append_unique(output, ["on_back", "lying", "spread_legs"])
    return output


def _adult_face_visibility_tags(tags):
    tag_set = set(tags or [])
    output = []
    if tag_set.intersection({
        "sex", "nude", "penetration", "doggystyle", "missionary",
        "girl_on_top", "cowgirl_position", "clothed_sex", "oral/fellatio",
        "fellatio", "deepthroat", "facial", "bukkake", "mating_press",
    }):
        _append_unique(output, ADULT_FACE_DETAIL_TAGS)
    if tag_set.intersection({"doggystyle"}):
        _append_unique(output, ADULT_BACK_POSE_FACE_TAGS)
    return output


def _adult_subject_count_tags(user_prompt, source_prompt, resolved_tags, adult_tags):
    output = _subject_count_tags(user_prompt, source_prompt, resolved_tags, "adult")
    if not set(adult_tags or []).intersection(ADULT_PARTNER_REQUIRED_TAGS):
        return output
    if _subject_count_implies_multiple(output):
        return output
    if len(resolved_tags or []) > 1:
        return output
    if "1girl" in output:
        return ["1girl", "1boy"]
    if "1boy" in output:
        return ["1girl", "1boy"]
    return output


def _adult_branch_anchor_tags(branch, seed_text, variation_strength=None):
    branch = str(branch or "").strip().lower()
    if not branch.startswith("adult_"):
        return []
    candidates = BRANCH_CURATED_SLOT_CANDIDATES.get(branch) or {}
    strength = max(1, _variation_strength_value(variation_strength or "balanced", {"scene_branch": branch}))
    slot_plan = (
        ("setting", 2),
        ("action", 1),
        ("pose", 1),
        ("atmosphere", 1),
    )
    if strength >= 2:
        slot_plan += (("prop", 1),)
    output = []
    for slot, count in slot_plan:
        pool = [tag for tag in candidates.get(slot) or () if _semantic_tag_allowed(tag)]
        picked = _stable_pick(pool, f"{seed_text}\nadult_branch_anchor\n{branch}\n{slot}", count)
        _append_unique(output, picked)
    return _filter_random_branch_conflicts(output, branch)


def compose_sdxl_adult_named_character_prompt(
    user_prompt,
    source_prompt="",
    resolution=None,
    variation_strength=None,
    prompt_variant_seed=None,
):
    adult_intent = detect_adult_intent(user_prompt, source_prompt)
    if not adult_intent.get("is_adult"):
        return {
            "prompt": "",
            "locked": False,
            "adult": False,
            "state": "not_adult",
            "reason": "No adult allowlist tag matched.",
            "adult_intent": adult_intent,
        }

    identity_user_prompt = _adult_identity_masked_text(user_prompt)
    identity_source_prompt = _adult_identity_masked_text(source_prompt)
    resolution = resolution or canvas_danbooru_service._canvas_requested_character_resolution(identity_user_prompt, identity_source_prompt)
    resolved_tags, copyright_tags = _expanded_identity_tags(identity_user_prompt, identity_source_prompt, resolution)
    blocked = sorted(set(resolved_tags or []).intersection(ADULT_BLOCKED_CHARACTER_TAGS))
    if blocked:
        return {
            "prompt": "",
            "locked": False,
            "adult": True,
            "state": "blocked",
            "reason": "adult_character_blocked",
            "blocked_tags": blocked,
            "adult_intent": adult_intent,
            "resolution": resolution,
        }

    adult_tags = adult_intent.get("tags") or []
    focused_adult_request = bool(
        resolved_tags
        and adult_tags
        and _adult_named_core_request_only(user_prompt, resolution, adult_tags)
    )
    variation_strength = variation_strength or ("light" if focused_adult_request else "rich")
    scene_user_prompt = _character_name_masked_text(user_prompt, resolution)
    scene_source_prompt = _character_name_masked_text(source_prompt, resolution)
    seed_text = json.dumps(
        {
            "adult_tags": adult_tags,
            "copyright_tags": copyright_tags,
            "prompt_variant_seed": prompt_variant_seed,
            "resolved_tags": resolved_tags,
            "scene_source_prompt": scene_source_prompt,
            "scene_user_prompt": scene_user_prompt,
            "user_prompt": user_prompt,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    branch = "adult_focus" if focused_adult_request else _random_choose_adult_branch(scene_user_prompt, scene_source_prompt, seed_text)
    composition_tags = _rule_tags(user_prompt, COMPOSITION_RULES)
    explicit_adult_scene_tags = _rule_tags(scene_user_prompt, ADULT_SCENE_RULES)
    explicit_scene_tags = []
    _append_unique(explicit_scene_tags, explicit_adult_scene_tags)
    _append_unique(explicit_scene_tags, _rule_tags(scene_user_prompt, SCENE_RULES))
    _append_unique(explicit_scene_tags, _semantic_candidate_tags(scene_user_prompt, scene_source_prompt))
    branch_anchor_tags = [] if focused_adult_request else _adult_branch_anchor_tags(branch, seed_text, variation_strength=variation_strength)
    branch_anchor_tags = _filter_random_branch_conflicts(branch_anchor_tags, branch)
    adult_intent_filter = {
        "scene_tags": list(dict.fromkeys(explicit_scene_tags + branch_anchor_tags)),
        "composition_tags": composition_tags,
        "scene_branch": branch,
        "detail_scene": not focused_adult_request,
        "plain_scene": False,
        "scene_mode": "focused" if focused_adult_request else "detailed",
    }

    output = []
    subject_count_tags = _adult_subject_count_tags(user_prompt, source_prompt, resolved_tags, adult_tags)
    _append_unique(output, subject_count_tags)
    if len(resolved_tags or []) <= 1 and not _subject_count_implies_multiple(subject_count_tags):
        _append_unique(output, ["solo"])
    _append_unique(output, resolved_tags)
    _append_unique(output, copyright_tags)
    _append_unique(output, adult_tags)
    if len(resolved_tags or []) > 1:
        _append_unique(output, ["couple"])
    _append_unique(output, composition_tags)
    _append_unique(output, explicit_scene_tags)
    _append_unique(output, branch_anchor_tags)
    if (
        not focused_adult_request
        and set(adult_tags or []).intersection(ADULT_PARTNER_REQUIRED_TAGS)
        and not set(output).intersection({"bathroom", "bathing", "showering", "bathtub", "onsen", "bedroom", "bed", "on_bed", "beach", "street", "city"})
    ):
        _append_unique(output, ["indoors", "bedroom"])
    _append_unique(output, _adult_focused_context_tags(adult_tags) if focused_adult_request else ADULT_CONTEXT_TAGS)
    _append_unique(output, _adult_face_visibility_tags(output))
    if focused_adult_request:
        adult_variant_tags = _adult_focused_support_tags(adult_tags)
    else:
        adult_variant_tags = _adult_variant_tags(
            adult_intent,
            user_prompt,
            source_prompt,
            output,
            variation_strength=variation_strength,
            variant_seed=prompt_variant_seed if prompt_variant_seed not in (None, "") else seed_text,
        )
    adult_variant_tags = _filter_random_branch_conflicts(adult_variant_tags, branch)
    _append_unique(output, adult_variant_tags)
    branch_variant_tags = [] if focused_adult_request else _curated_branch_variant_tags(
        adult_intent_filter,
        scene_user_prompt,
        resolved_tags,
        copyright_tags,
        variation_strength=variation_strength,
        variant_seed=prompt_variant_seed if prompt_variant_seed not in (None, "") else seed_text,
    )
    branch_variant_tags = _filter_random_branch_conflicts(branch_variant_tags, branch)
    _append_unique(output, branch_variant_tags)
    spice_tags = [] if focused_adult_request else _random_creative_spice_tags(seed_text, branch, adult=True)
    _append_unique(output, spice_tags)
    adult_intent_filter["scene_tags"] = list(dict.fromkeys(
        adult_intent_filter["scene_tags"] + adult_variant_tags + branch_variant_tags + spice_tags
    ))
    output = _filter_random_branch_conflicts(output, branch)
    explicit_bed_scene = set(_rule_tags(scene_user_prompt, SCENE_RULES)).intersection({"bedroom", "bed", "on_bed"})
    if explicit_bed_scene:
        output = [
            tag for tag in output
            if tag not in {"bathroom", "bathing", "showering", "bathtub", "shower_head", "onsen"}
        ]
        _append_unique(output, ["indoors", "bedroom", "bed", "on_bed", "pillow"])
    explicit_bath_scene = set(_rule_tags(scene_user_prompt, ADULT_SCENE_RULES)).intersection({"bathroom", "bathing", "showering", "bathtub", "shower_head", "onsen"})
    if set(adult_tags or []).intersection({"doggystyle", "missionary", "girl_on_top", "cowgirl_position", "anal"}) and not explicit_bath_scene:
        output = [
            tag for tag in output
            if tag not in {"bathroom", "bathing", "showering", "bathtub", "shower_head", "onsen"}
        ]
        _append_unique(output, ["indoors", "bedroom", "bed"])
    adult_level = _adult_intent_level(adult_tags, user_prompt, source_prompt)
    adult_negative_removed = []
    output = _apply_user_explicit_conflict_filters(output, adult_intent_filter)
    output = _apply_adult_conflict_filters(output, adult_tags=adult_tags, explicit_full_body="full_body" in set(composition_tags or []))
    adult_explicit_tags = []
    _append_unique(adult_explicit_tags, adult_tags)
    _append_unique(adult_explicit_tags, subject_count_tags)
    _append_unique(adult_explicit_tags, composition_tags)
    _append_unique(adult_explicit_tags, explicit_scene_tags)
    output, adult_negative_removed = _apply_adult_negative_conflict_filters(
        output,
        adult_tags=adult_tags,
        explicit_tags=adult_explicit_tags,
        preferred_tags=list(branch_anchor_tags) + list(adult_variant_tags) + list(branch_variant_tags) + list(spice_tags),
        return_removed=True,
    )
    adult_intent_filter["scene_tags"] = _apply_adult_negative_conflict_filters(
        adult_intent_filter.get("scene_tags") or [],
        adult_tags=adult_tags,
        explicit_tags=explicit_scene_tags,
        preferred_tags=list(branch_anchor_tags) + list(adult_variant_tags) + list(branch_variant_tags) + list(spice_tags),
    )
    adult_intent_filter["adult_negative_conflict_removed"] = adult_negative_removed[:16]
    output = _apply_bathing_scene_conflict_filters(output, adult_intent_filter)
    output = _apply_bed_scene_conflict_filters(output, adult_intent_filter)
    output = _apply_beach_scene_conflict_filters(output, adult_intent_filter)
    output = _apply_street_scene_conflict_filters(output, adult_intent_filter)
    output = _apply_major_scene_conflict_filters(output, adult_intent_filter)
    output = _apply_explicit_visual_bias_filters(output, user_prompt, source_prompt)
    if (
        focused_adult_request
        and set(adult_tags or []).intersection(ADULT_SPECIFIC_POSITION_TAGS)
        and "full_body" not in set(composition_tags or [])
    ):
        output = [tag for tag in output if tag != "full_body"]
    output = _sanitize_final_canonical_tags(
        output,
        user_prompt,
        source_prompt=source_prompt,
        resolved_tags=resolved_tags,
        copyright_tags=copyright_tags,
        intent=adult_intent_filter,
        subject_count_tags=subject_count_tags,
    )

    return {
        "prompt": _prompt_text_from_tags(
            output,
            user_prompt,
            source_prompt=source_prompt,
            resolved_tags=resolved_tags,
            copyright_tags=copyright_tags,
            variation_strength=variation_strength,
            prompt_variant_seed=prompt_variant_seed,
        ),
        "locked": True,
        "adult": True,
        "state": "ok",
        "intent": adult_intent_filter,
        "adult_intent": adult_intent,
        "resolution": resolution,
        "resolved_tags": resolved_tags,
        "copyright_tags": copyright_tags,
        "allowlist_source": "tags/weilin_tagcart.csv:NSFW",
        "adult_level": adult_level,
        "scene_branch": branch,
        "branch_anchor_tags": [tag for tag in branch_anchor_tags if tag in output],
        "branch_variant_tags": [tag for tag in branch_variant_tags if tag in output],
        "spice_tags": [tag for tag in spice_tags if tag in output],
        "adult_variant_tags": adult_variant_tags,
        "adult_negative_conflict_removed": adult_negative_removed[:16],
        "variation_seed": prompt_variant_seed if prompt_variant_seed not in (None, "") else seed_text,
    }


def _stable_pick(tags, seed_text, count=1):
    unique = [tag for tag in tags or [] if tag]
    if not unique or count <= 0:
        return []
    scored = []
    for tag in unique:
        digest = hashlib.sha256((str(seed_text or "") + "\n" + tag).encode("utf-8", "ignore")).hexdigest()
        scored.append((digest, tag))
    scored.sort()
    return [tag for _, tag in scored[:count]]


def _random_unit_float(seed_text, salt=""):
    digest = hashlib.sha256((str(seed_text or "") + "\n" + str(salt or "")).encode("utf-8", "ignore")).hexdigest()
    return int(digest[:12], 16) / float(0xFFFFFFFFFFFF)


def _random_choice(items, seed_text, salt=""):
    values = [item for item in (items or []) if item]
    if not values:
        return None
    index = int(_random_unit_float(seed_text, salt) * len(values))
    return values[min(index, len(values) - 1)]


def _random_prompt_has_named_identity(user_prompt, source_prompt=""):
    source = "\n".join(str(item or "") for item in (user_prompt, source_prompt) if str(item or "").strip())
    direct_resolved, direct_copyright = _direct_identity_tags(source)
    if direct_resolved or direct_copyright:
        return True
    try:
        resolution = canvas_danbooru_service._canvas_requested_character_resolution(user_prompt, source_prompt)
    except Exception:
        resolution = {}
    has_resolution = bool(
        isinstance(resolution, dict)
        and resolution.get("state") == "resolved"
        and resolution.get("resolved")
    )
    if not has_resolution:
        return False
    has_random_word = any(re.search(pattern, source, re.I) for pattern in RANDOM_IMAGE_INTENT_PATTERNS)
    has_image_context = any(re.search(pattern, source, re.I) for pattern in RANDOM_IMAGE_CONTEXT_PATTERNS)
    if has_random_word and has_image_context and _rule_tags(source, SCENE_RULES):
        return False
    return True


def _random_prompt_has_explicit_pronoun_subject(user_prompt, source_prompt=""):
    source = "\n".join(str(item or "") for item in (user_prompt, source_prompt) if str(item or "").strip())
    if not source.strip():
        return False
    if re.search(r"(?:\u7ed9\u4f60|\u70ba\u4f60|\u4e3a\u4f60).{0,12}(?:\u753b|\u756b|\u751f\u6210|draw|make|generate)", source, re.I):
        return False
    if re.search(
        r"(?:\u753b|\u756b|\u6765\u5f20|\u4f86\u5f35|\u751f\u6210|\u770b|\u770b\u770b).{0,8}"
        r"(?:\u4f60|\u4f60\u7684(?:\u8272\u56fe|\u8272\u5716|\u6da9\u56fe|\u6f80\u5716|\u8eab\u4f53|\u8eab\u9ad4|\u88f8\u4f53|\u88f8\u9ad4|\u81ea\u62cd|\u5934\u50cf|\u982d\u50cf|\u7acb\u7ed8|\u7acb\u7e6a|\u6837\u5b50|\u6a23\u5b50|\u5916\u89c2|\u5916\u89c0|\u5f62\u8c61))",
        source,
        re.I,
    ):
        return True
    if re.search(
        r"(?:\u4f60\u7684)(?:\u8272\u56fe|\u8272\u5716|\u6da9\u56fe|\u6f80\u5716|\u8eab\u4f53|\u8eab\u9ad4|\u88f8\u4f53|\u88f8\u9ad4|\u81ea\u62cd|\u5934\u50cf|\u982d\u50cf|\u7acb\u7ed8|\u7acb\u7e6a|\u6837\u5b50|\u6a23\u5b50|\u5916\u89c2|\u5916\u89c0|\u5f62\u8c61)",
        source,
        re.I,
    ):
        return True
    return bool(re.search(
        r"\b(?:your\s+(?:body|nude|nudes|naked\s+body|selfie|avatar|appearance|look|image|picture)|"
        r"(?:draw|show|make|generate|see|view)\s+(?:you|yourself|your\s+(?:body|nude|naked\s+body|selfie|avatar|appearance|look|image|picture)))\b",
        source,
        re.I,
    ))


def detect_random_image_intent(user_prompt, source_prompt=""):
    combined = "\n".join(item for item in (str(user_prompt or ""), str(source_prompt or "")) if item)
    if not combined.strip():
        return {
            "is_random": False,
            "is_adult": False,
            "tags": [],
            "reason": "empty",
        }
    has_random_word = any(re.search(pattern, combined, re.I) for pattern in RANDOM_IMAGE_INTENT_PATTERNS)
    has_image_context = any(re.search(pattern, combined, re.I) for pattern in RANDOM_IMAGE_CONTEXT_PATTERNS)
    adult_intent = detect_adult_intent(user_prompt, source_prompt)
    is_adult = bool(adult_intent.get("is_adult"))
    adult_image_context = bool(re.search(r"\u56fe|\u5716|\u753b|\u756b|\u6765\u4e2a|\u4f86\u500b|\u6765\u5f20|\u4f86\u5f35|image|picture|prompt|draw|make|generate", combined, re.I))
    has_pronoun_subject = _random_prompt_has_explicit_pronoun_subject(user_prompt, source_prompt)
    has_named_identity = _random_prompt_has_named_identity(user_prompt, source_prompt) or has_pronoun_subject
    if is_adult and adult_image_context and not has_named_identity:
        has_image_context = True
        has_random_word = has_random_word or bool(re.search(r"\u6765|\u4f86|\u753b|\u756b|draw|make|generate", combined, re.I))
    is_random = bool(has_random_word and has_image_context and not has_named_identity)
    return {
        "is_random": is_random,
        "is_adult": bool(is_random and is_adult),
        "tags": list(adult_intent.get("tags") or []) if is_random else [],
        "adult_intent": adult_intent,
        "explicit_scenery": bool(any(re.search(pattern, combined, re.I) for pattern in RANDOM_IMAGE_EXPLICIT_SCENERY_PATTERNS)),
        "reason": "explicit_pronoun_subject" if has_pronoun_subject else "named_character_present" if has_named_identity else "matched_random_image" if is_random else "not_random_image",
    }


def _random_character_row_has_minor_risk(row):
    source = " ".join(
        str((row or {}).get(key) or "")
        for key in ("tag", "translation", "aliases", "group", "source_term", "_merged_lookup_values")
    )
    return bool(RANDOM_ADULT_MINOR_RISK_PATTERN.search(source))


def _random_character_row_is_placeholder(row):
    tag = _clean_tag((row or {}).get("tag"))
    if not tag:
        return True
    source = " ".join(
        str((row or {}).get(key) or "")
        for key in ("tag", "translation", "aliases", "group", "source_term", "_merged_lookup_values")
    ).lower()
    if tag in RANDOM_POPULAR_CHARACTER_EXCLUDED_TAGS:
        return True
    if re.search(r"(?:^|[_\s(])(?:sensei|teacher|admiral|commander|producer|doctor|trainer|master|captain)(?:$|[_\s)])", source, re.I):
        return True
    if re.search(r"(?:player|protagonist|avatar|self_insert|original_character|anonymous|mob_character)", source, re.I):
        return True
    return False


@functools.lru_cache(maxsize=1)
def _random_popular_character_rows():
    try:
        index = canvas_danbooru_service._canvas_load_danbooru_character_index()
    except Exception:
        index = {}
    rows = []
    seen = set()
    for row in (index.get("rows") or []):
        if not isinstance(row, dict) or row.get("category") != "character":
            continue
        tag = _clean_tag(row.get("tag"))
        if not tag or tag in seen:
            continue
        count = int(row.get("count") or 0)
        if count < RANDOM_POPULAR_CHARACTER_MIN_COUNT:
            continue
        if _random_character_row_is_placeholder(row):
            continue
        item = dict(row)
        item["tag"] = tag
        item["count"] = count
        rows.append(item)
        seen.add(tag)
    rows.sort(key=lambda item: int(item.get("count") or 0), reverse=True)
    limited = rows[:RANDOM_POPULAR_CHARACTER_POOL_LIMIT]
    for index, item in enumerate(limited, start=1):
        item["_random_rank"] = index
        count = int(item.get("count") or 0)
        if index <= RANDOM_POPULAR_CHARACTER_HEAD_LIMIT:
            bucket = "head"
        elif count >= 1500:
            bucket = "popular"
        elif count >= 300:
            bucket = "mid_tail"
        else:
            bucket = "long_tail"
        item["_random_bucket"] = bucket
    return tuple(limited)


def _select_random_popular_character(seed_text, adult=False):
    rows = list(_random_popular_character_rows())
    if adult:
        rows = [
            row for row in rows
            if int(row.get("count") or 0) >= RANDOM_ADULT_CHARACTER_MIN_COUNT
            and not _random_character_row_has_minor_risk(row)
            and not _random_character_row_is_placeholder(row)
        ]
    if not rows:
        return {}
    bucket = "popular" if adult else str(_random_choice(RANDOM_CHARACTER_BUCKET_WEIGHTS, seed_text, "character_bucket") or "wide")
    bucket_rows = rows if bucket == "wide" else [row for row in rows if row.get("_random_bucket") == bucket]
    if not bucket_rows:
        bucket_rows = rows
    picked = dict(_random_choice(bucket_rows, seed_text, f"popular_character:{bucket}") or {})
    picked["_random_bucket"] = picked.get("_random_bucket") or bucket
    return picked


def _persona_tags_from_prompt_intent(prompt_intent):
    normalized = normalize_structured_prompt_intent(prompt_intent)
    output = []
    for tag in normalized.get("locked_tags") or []:
        clean = _clean_tag(tag)
        if clean and clean not in output:
            output.append(clean)
    if isinstance(prompt_intent, dict):
        for key in ("required_prompt_tags", "scene_tags", "subject_count_tags"):
            for tag in prompt_intent.get(key) or []:
                clean = _clean_tag(tag)
                if clean and clean not in output:
                    output.append(clean)
    return output


def _random_subject_count_tags(identity_tags, prompt_intent=None):
    tags = [_clean_tag(tag) for tag in (identity_tags or []) if _clean_tag(tag)]
    for tag in tags:
        if tag in SUBJECT_COUNT_TAGS:
            return [tag]
    if isinstance(prompt_intent, dict):
        for tag in prompt_intent.get("subject_count_tags") or []:
            clean = _clean_tag(tag)
            if clean in SUBJECT_COUNT_TAGS:
                return [clean]
    for tag in tags:
        hinted = CHARACTER_SUBJECT_COUNT_HINTS.get(tag)
        if hinted:
            return [hinted]
    return ["1girl"]


def _subject_counts_from_count_tags(tags):
    tag_set = set(_clean_tag(tag) for tag in tags or ())
    girls = 0
    boys = 0
    others = 0
    for tag in tag_set:
        match = re.fullmatch(r"([1-6])girls", tag or "")
        if match:
            girls = max(girls, int(match.group(1)))
        match = re.fullmatch(r"([1-6])boys", tag or "")
        if match:
            boys = max(boys, int(match.group(1)))
    if "1girl" in tag_set:
        girls = max(girls, 1)
    if "1boy" in tag_set:
        boys = max(boys, 1)
    if "multiple_others" in tag_set:
        others = max(others, 1)
    total = max(girls + boys + others, 0 if "no_humans" in tag_set else girls + boys + others)
    return {"girls": girls, "boys": boys, "others": others, "total": total}


def _random_resolution_from_character_row(row):
    tag = _clean_tag((row or {}).get("tag"))
    if not tag:
        return {"state": "none", "resolved": [], "candidates": [], "copyright_candidates": []}
    return {
        "state": "resolved",
        "resolved": [dict(row, tag=tag, category="character")],
        "candidates": [],
        "copyright_candidates": [],
        "source": "random_popular_danbooru",
    }


def _random_choose_adult_branch(user_prompt, source_prompt, seed_text):
    combined = "\n".join(item for item in (str(user_prompt or ""), str(source_prompt or "")) if item).lower()
    if re.search(r"\u6d74|\u6fa1|\u6e29\u6cc9|\u6eab\u6cc9|\u6cf3\u6c60|\b(?:bath|shower|onsen|hot\s+spring|pool)\b", combined, re.I):
        if re.search(r"\u6cf3\u6c60|\bpool\b", combined, re.I):
            return "adult_pool"
        return "adult_onsen"
    if re.search(r"\u6d77|\u6c99\u6ee9|\u6c99\u7058|\bbeach\b|\bocean\b|\bsea\b", combined, re.I):
        return "adult_beach"
    if re.search(r"\u5e8a|\u5367\u5ba4|\u81e5\u5ba4|\bbed(?:room)?\b", combined, re.I):
        return "adult_bedroom"
    if re.search(r"\u821e\u53f0|\u8868\u6f14|\u5076\u50cf|\bstage\b|\bconcert\b|\bidol\b", combined, re.I):
        return "adult_stage"
    return str(_random_choice(RANDOM_ADULT_BRANCHES, seed_text, "adult_scene_branch") or "adult_bedroom")


def _random_choose_branch(user_prompt, source_prompt, seed_text, adult=False):
    if adult:
        return _random_choose_adult_branch(user_prompt, source_prompt, seed_text)
    plan = plan_prompt_intent(user_prompt, source_prompt)
    branch = str((plan or {}).get("scene_branch") or "").strip().lower()
    if branch and branch != "generic":
        return branch
    return str(_random_choice(RANDOM_DEFAULT_BRANCHES, seed_text, "scene_branch") or "leisure")


def _filter_random_branch_conflicts(tags, branch):
    branch = str(branch or "").strip().lower()
    blocked = set(RANDOM_GENERAL_BRANCH_BLOCKED_TAGS.get(branch) or ())
    blocked.update(RANDOM_ADULT_BRANCH_BLOCKED_TAGS.get(branch) or ())
    if branch.startswith("adult_"):
        blocked.update(RANDOM_ADULT_GLOBAL_BLOCKED_TAGS)
    if not blocked:
        return list(tags or [])
    return [tag for tag in (tags or []) if _clean_tag(tag) not in blocked]


def _random_creative_spice_tags(seed_text, branch, adult=False):
    pool = RANDOM_ADULT_SPICE_TAGS if adult else RANDOM_GENERAL_SPICE_TAGS
    count = 2 if adult else 3
    picked = _stable_pick(pool, f"{seed_text}\n{branch}\ncreative_spice", count)
    picked = _filter_random_branch_conflicts(picked, branch)
    return [tag for tag in picked if _semantic_tag_allowed(tag)]


def _random_generation_resolution(seed_text, user_prompt="", source_prompt=""):
    combined = "\n".join(item for item in (str(user_prompt or ""), str(source_prompt or "")) if item).lower()
    choices = list(RANDOM_IMAGE_RESOLUTION_CHOICES)
    if re.search(r"\u7ad6\u56fe|\u7ad6\u5716|\u7ad6\u7248|\u7ad6\u5c4f|\u7eb5\u5411|\u7e31\u5411|portrait|vertical|\b2\s*[:x/]\s*3\b|\b9\s*[:x/]\s*16\b", combined, re.I):
        choices = [item for item in choices if item.get("key") == "portrait_2x3"]
    elif re.search(r"\u6a2a\u56fe|\u6a2a\u5716|\u6a2a\u7248|\u6a2a\u5c4f|\u6a2a\u5411|landscape|horizontal|wide|\b3\s*[:x/]\s*2\b|\b16\s*[:x/]\s*9\b", combined, re.I):
        choices = [item for item in choices if item.get("key") == "landscape_3x2"]
    elif re.search(r"\u65b9\u56fe|\u65b9\u5716|\u6b63\u65b9\u5f62|square|\b1\s*[:x/]\s*1\b", combined, re.I):
        choices = [item for item in choices if item.get("key") == "square_1x1"]
    picked = dict(_random_choice(choices or list(RANDOM_IMAGE_RESOLUTION_CHOICES), seed_text, "generation_resolution") or RANDOM_IMAGE_RESOLUTION_CHOICES[-1])
    picked["source"] = "backend_random_sdxl"
    return picked


def _random_subject_plan(user_prompt, source_prompt="", prompt_variant_seed=None, prompt_intent=None):
    random_intent = detect_random_image_intent(user_prompt, source_prompt)
    seed_text = json.dumps(
        {
            "user_prompt": user_prompt,
            "source_prompt": source_prompt,
            "prompt_variant_seed": prompt_variant_seed,
            "random_intent": random_intent,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    adult = bool(random_intent.get("is_adult"))
    persona_tags = _persona_tags_from_prompt_intent(prompt_intent)
    persona_available = bool(persona_tags)
    use_persona = bool(persona_available and _random_unit_float(seed_text, "subject_source") < RANDOM_PERSONA_PROBABILITY)
    if use_persona:
        count_tags = _random_subject_count_tags(persona_tags, prompt_intent=prompt_intent)
        identity_tags = [tag for tag in persona_tags if tag not in SUBJECT_COUNT_TAGS and tag != "solo"]
        return {
            "random_intent": random_intent,
            "subject_source": "persona",
            "identity_tags": identity_tags,
            "subject_count_tags": count_tags,
            "subject_counts": _subject_counts_from_count_tags(count_tags),
            "display_name": "assistant persona",
            "display_name_zh": "助手人设角色",
            "character_row": {},
            "resolution": {"state": "none", "resolved": [], "candidates": [], "copyright_candidates": []},
            "seed_text": seed_text,
        }
    row = _select_random_popular_character(seed_text, adult=adult)
    if row:
        tag = _clean_tag(row.get("tag"))
        count_tags = _random_subject_count_tags([tag])
        bucket = str(row.get("_random_bucket") or "wide").strip() or "wide"
        return {
            "random_intent": random_intent,
            "subject_source": f"popular_danbooru:{bucket}",
            "subject_bucket": bucket,
            "subject_rank": int(row.get("_random_rank") or 0),
            "identity_tags": [tag],
            "subject_count_tags": count_tags,
            "subject_counts": _subject_counts_from_count_tags(count_tags),
            "display_name": _tag_to_english_phrase(tag),
            "display_name_zh": str(row.get("translation") or "").strip() or _tag_to_english_phrase(tag),
            "character_row": row,
            "resolution": _random_resolution_from_character_row(row),
            "seed_text": seed_text,
        }
    count_tags = ["1girl"]
    return {
        "random_intent": random_intent,
        "subject_source": "generic_adult" if adult else "generic_character",
        "identity_tags": ["original"],
        "subject_count_tags": count_tags,
        "subject_counts": _subject_counts_from_count_tags(count_tags),
        "display_name": "an original adult woman" if adult else "an original anime character",
        "display_name_zh": "原创成年女性角色" if adult else "原创动漫角色",
        "character_row": {},
        "resolution": {"state": "none", "resolved": [], "candidates": [], "copyright_candidates": []},
        "seed_text": seed_text,
    }


def _ensure_random_story_tags(output, branch, user_prompt, subject_plan, variation_strength=None, prompt_variant_seed=None):
    intent = plan_prompt_intent(user_prompt, "")
    intent = dict(intent)
    intent["scene_branch"] = branch or "generic"
    if not intent.get("scene_tags"):
        intent["scene_tags"] = []
    variant_tags = _curated_branch_variant_tags(
        intent,
        user_prompt,
        subject_plan.get("identity_tags") or [],
        [],
        variation_strength=variation_strength or "rich",
        variant_seed=prompt_variant_seed or subject_plan.get("seed_text"),
    )
    _append_unique(output, variant_tags)
    intent["scene_tags"] = list(dict.fromkeys((intent.get("scene_tags") or []) + list(variant_tags or [])))
    _ensure_story_facets(output, variant_tags, intent)
    return intent, variant_tags


def compose_sdxl_random_character_prompt(
    user_prompt,
    source_prompt="",
    variation_strength=None,
    prompt_variant_seed=None,
    prompt_intent=None,
):
    random_intent = detect_random_image_intent(user_prompt, source_prompt)
    if not random_intent.get("is_random"):
        return {"locked": False, "prompt": "", "random": False, "random_intent": random_intent}
    subject_plan = _random_subject_plan(
        user_prompt,
        source_prompt=source_prompt,
        prompt_variant_seed=prompt_variant_seed,
        prompt_intent=prompt_intent,
    )
    adult = bool(random_intent.get("is_adult"))
    branch = _random_choose_branch(user_prompt, source_prompt, subject_plan.get("seed_text"), adult=adult)
    adult_tags = list(random_intent.get("tags") or [])
    if adult and not adult_tags:
        adult_tags = ["nude"]
    adult_variant_tags = []

    output = []
    subject_count_tags = list(subject_plan.get("subject_count_tags") or ["1girl"])
    _append_unique(output, subject_count_tags)
    if subject_count_tags in (["1girl"], ["1boy"]):
        _append_unique(output, ["solo"])
    _append_unique(output, subject_plan.get("identity_tags") or [])
    if adult:
        _append_unique(output, adult_tags)
        _append_unique(output, _rule_tags(user_prompt, ADULT_SCENE_RULES))
        _append_unique(output, ADULT_CONTEXT_TAGS)
        _append_unique(output, _adult_face_visibility_tags(output))
        adult_intent = {"is_adult": True, "tags": adult_tags, "allowlist_source": "tags/weilin_tagcart.csv:NSFW"}
        adult_variant_tags = _adult_variant_tags(
            adult_intent,
            user_prompt,
            source_prompt,
            output,
            variation_strength=variation_strength or "balanced",
            variant_seed=prompt_variant_seed or subject_plan.get("seed_text"),
        )
        adult_variant_tags = _filter_random_branch_conflicts(adult_variant_tags, branch)
        _append_unique(output, adult_variant_tags)
    _append_unique(output, _rule_tags(user_prompt, COMPOSITION_RULES))
    _append_unique(output, _rule_tags(user_prompt, SCENE_RULES))
    intent, variant_tags = _ensure_random_story_tags(
        output,
        branch,
        user_prompt,
        subject_plan,
        variation_strength=variation_strength or "rich",
        prompt_variant_seed=prompt_variant_seed,
    )
    variant_tags = _filter_random_branch_conflicts(variant_tags, branch)
    spice_tags = _random_creative_spice_tags(subject_plan.get("seed_text"), branch, adult=adult)
    _append_unique(output, spice_tags)
    intent["scene_tags"] = list(dict.fromkeys((intent.get("scene_tags") or []) + spice_tags))
    composition_archetype = _random_composition_archetype(subject_plan.get("seed_text"), branch=branch, adult=adult)
    sfw_trigger_scene_tags = [] if adult else _sfw_primary_scene_trigger_tags(user_prompt, source_prompt)
    database_enrichment_tags = _random_database_enrichment_tags(
        subject_plan.get("seed_text"),
        branch,
        composition_archetype,
        user_prompt=user_prompt,
        source_prompt=source_prompt,
        scene_tags=sfw_trigger_scene_tags,
        adult=adult,
        variation_strength=variation_strength or "balanced",
    )
    database_enrichment_tags = _filter_random_branch_conflicts(database_enrichment_tags, branch)
    sfw_association_triggers = [] if adult else _sfw_prompt_trigger_tags(
        user_prompt,
        source_prompt=source_prompt,
        scene_tags=sfw_trigger_scene_tags,
        branch=branch,
    )
    sfw_association_candidates = set() if adult else set(_sfw_association_tags_for_prompt(
        user_prompt,
        source_prompt=source_prompt,
        scene_tags=sfw_trigger_scene_tags,
        branch=branch,
    ))
    sfw_association_tags = [tag for tag in database_enrichment_tags if tag in sfw_association_candidates]
    _append_unique(output, database_enrichment_tags)
    intent["scene_tags"] = list(dict.fromkeys((intent.get("scene_tags") or []) + database_enrichment_tags))
    output = _filter_random_branch_conflicts(output, branch)
    intent["scene_tags"] = _filter_random_branch_conflicts(intent.get("scene_tags") or [], branch)
    if adult:
        intent["scene_branch"] = branch
        intent["scene_tags"] = list(dict.fromkeys((intent.get("scene_tags") or []) + variant_tags + adult_tags + spice_tags + database_enrichment_tags))
        intent["scene_tags"] = _filter_random_branch_conflicts(intent.get("scene_tags") or [], branch)
        output = _apply_adult_conflict_filters(output, adult_tags=adult_tags)
    output = _limit_random_camera_bias_tags(output, subject_plan.get("seed_text"), composition_archetype, user_prompt, source_prompt)
    intent["scene_tags"] = _limit_random_camera_bias_tags(intent.get("scene_tags") or [], subject_plan.get("seed_text"), composition_archetype, user_prompt, source_prompt)
    if set(output).intersection({"1girl", "1boy", "2girls", "2boys", "3girls", "3boys"}):
        output = [tag for tag in output if tag != "no_humans"]
    output = _apply_user_explicit_conflict_filters(output, intent)
    output = _apply_indoor_scene_conflict_filters(output, intent)
    output = _apply_bathing_scene_conflict_filters(output, intent)
    output = _apply_bed_scene_conflict_filters(output, intent)
    output = _apply_beach_scene_conflict_filters(output, intent)
    output = _apply_street_scene_conflict_filters(output, intent)
    output = _apply_major_scene_conflict_filters(output, intent)
    output = _apply_explicit_visual_bias_filters(output, user_prompt, source_prompt)
    _ensure_story_facets(output, [], intent)
    sfw_negative_removed = []
    adult_negative_removed = []
    if not adult:
        sfw_explicit_tags = []
        _append_unique(sfw_explicit_tags, _rule_tags(user_prompt, SCENE_RULES))
        _append_unique(sfw_explicit_tags, _rule_tags(source_prompt, SCENE_RULES))
        _append_unique(sfw_explicit_tags, sfw_trigger_scene_tags)
        output, sfw_negative_removed = _apply_sfw_negative_conflict_filters(
            output,
            explicit_tags=sfw_explicit_tags,
            preferred_tags=sfw_association_tags,
            return_removed=True,
        )
        intent["scene_tags"] = _apply_sfw_negative_conflict_filters(
            intent.get("scene_tags") or [],
            explicit_tags=sfw_explicit_tags,
            preferred_tags=sfw_association_tags,
        )
    if adult:
        adult_explicit_tags = []
        _append_unique(adult_explicit_tags, adult_tags)
        _append_unique(adult_explicit_tags, _rule_tags(user_prompt, ADULT_SCENE_RULES))
        _append_unique(adult_explicit_tags, _rule_tags(source_prompt, ADULT_SCENE_RULES))
        _append_unique(adult_explicit_tags, _rule_tags(user_prompt, SCENE_RULES))
        _append_unique(adult_explicit_tags, _rule_tags(source_prompt, SCENE_RULES))
        output, adult_negative_removed = _apply_adult_negative_conflict_filters(
            output,
            adult_tags=adult_tags,
            explicit_tags=adult_explicit_tags,
            preferred_tags=list(adult_variant_tags) + list(variant_tags) + list(spice_tags) + list(database_enrichment_tags),
            return_removed=True,
        )
        intent["scene_tags"] = _apply_adult_negative_conflict_filters(
            intent.get("scene_tags") or [],
            adult_tags=adult_tags,
            explicit_tags=adult_explicit_tags,
            preferred_tags=list(adult_variant_tags) + list(variant_tags) + list(spice_tags) + list(database_enrichment_tags),
        )
        output = _apply_adult_conflict_filters(output, adult_tags=adult_tags)
    _append_unique(output, canvas_danbooru_policy.QUALITY_TAGS)
    resolved_tags = (
        list(subject_plan.get("identity_tags") or [])
        if str(subject_plan.get("subject_source") or "").startswith("popular_danbooru")
        else []
    )
    output = _sanitize_final_canonical_tags(
        output,
        user_prompt,
        source_prompt=source_prompt,
        resolved_tags=resolved_tags,
        copyright_tags=[],
        intent=intent,
        subject_count_tags=subject_count_tags,
    )
    output = _limit_random_prompt_tags(output)
    prompt = _prompt_text_from_tags(
        output,
        user_prompt,
        source_prompt=source_prompt,
        resolved_tags=resolved_tags,
        copyright_tags=[],
        variation_strength=variation_strength or "rich",
        prompt_variant_seed=prompt_variant_seed,
    )
    generation_resolution = _random_generation_resolution(subject_plan.get("seed_text"), user_prompt, source_prompt)
    locked_tags = []
    _append_unique(locked_tags, subject_count_tags)
    _append_unique(locked_tags, subject_plan.get("identity_tags") or [])
    _append_unique(locked_tags, adult_tags)
    _append_unique(locked_tags, [tag for tag in output if tag in SETTING_TAG_POOL or tag in ACTION_TAG_POOL or tag in POSE_TAG_POOL or tag in ATMOSPHERE_TAG_POOL][:10])
    composer_meta = {
        "random": True,
        "subject_source": subject_plan.get("subject_source"),
        "subject_bucket": subject_plan.get("subject_bucket") or "",
        "prompt_format": "danbooru_tags",
        "scene_branch": intent.get("scene_branch") or branch,
        "composition_archetype": composition_archetype,
        "variation_seed": prompt_variant_seed if prompt_variant_seed not in (None, "") else subject_plan.get("seed_text"),
        "facet_counts": _facet_counts(output),
        "adult_variant_tags": [tag for tag in adult_variant_tags if tag in output][:16] if adult else [],
        "adult_negative_conflict_removed": adult_negative_removed[:16] if adult else [],
        "sfw_association_triggers": sfw_association_triggers[:16],
        "sfw_association_tags": [tag for tag in sfw_association_tags if tag in output][:16],
        "sfw_negative_conflict_removed": sfw_negative_removed[:16],
        "database_enrichment_tags": [tag for tag in database_enrichment_tags if tag in output][:16],
        "generation_resolution": generation_resolution,
        "random_intent": random_intent,
        "subject": {
            "tag": (subject_plan.get("identity_tags") or [""])[0],
            "display_name": subject_plan.get("display_name"),
            "display_name_zh": subject_plan.get("display_name_zh"),
            "bucket": subject_plan.get("subject_bucket") or "",
            "rank": subject_plan.get("subject_rank") or 0,
            "count": int((subject_plan.get("character_row") or {}).get("count") or 0),
        },
    }
    return {
        "prompt": prompt,
        "locked": bool(prompt),
        "random": True,
        "adult": adult,
        "adult_intent": random_intent.get("adult_intent"),
        "subject_counts": subject_plan.get("subject_counts") or _subject_counts_from_count_tags(subject_count_tags),
        "prompt_intent": {
            "locked_tags": locked_tags[:24],
            "must_preserve": ["random character prompt", "visible character subject"],
            "enrichment_tags": [tag for tag in list(variant_tags) + spice_tags + database_enrichment_tags if tag not in locked_tags][:16],
            "sfw_association_triggers": sfw_association_triggers[:16],
            "sfw_association_tags": [tag for tag in sfw_association_tags if tag not in locked_tags][:16],
            "sfw_negative_conflict_removed": sfw_negative_removed[:16],
            "adult_negative_conflict_removed": adult_negative_removed[:16] if adult else [],
            "scene_strictness": "high",
            "scene_branch": intent.get("scene_branch") or branch,
            "composition_archetype": composition_archetype,
        },
        "intent": intent,
        "resolution": subject_plan.get("resolution") or {},
        "generation_resolution": generation_resolution,
        "resolved_tags": resolved_tags,
        "copyright_tags": [],
        "scene_tag_count": _scene_tag_count(output),
        "story_facet_counts": _facet_counts(output),
        "prompt_composer": composer_meta,
    }


NATURAL_TAG_ZH = {
    "city": "城市街景",
    "street": "街道",
    "indoors": "室内空间",
    "bedroom": "卧室",
    "bathroom": "浴室",
    "beach": "海边",
    "ocean": "海面",
    "sea": "海面",
    "water": "水边",
    "pool": "泳池边",
    "poolside": "泳池边",
    "school": "校园",
    "classroom": "教室",
    "forest": "森林",
    "garden": "花园",
    "cafe": "咖啡馆",
    "backpack": "背包",
    "camera": "相机",
    "map": "地图",
    "suitcase": "行李箱",
    "standing": "站立",
    "sitting": "坐着",
    "walking": "行走",
    "running": "奔跑",
    "swimming": "游泳",
    "sleeping": "安静入睡",
    "lying": "躺着",
    "holding": "拿着道具",
    "holding_cup": "端着杯子",
    "holding_book": "拿着书",
    "fighting": "做出战斗动作",
    "bathing": "沐浴",
    "showering": "淋浴",
    "nude": "成人向裸露",
    "kiss": "亲吻",
    "full_body": "全身构图",
    "upper_body": "半身构图",
    "cowboy_shot": "中景构图",
    "portrait": "肖像构图",
    "looking_at_viewer": "看向镜头",
    "dynamic_pose": "动态姿势",
    "soft_lighting": "柔和光线",
    "cinematic_lighting": "电影感光影",
    "depth_of_field": "浅景深",
    "blurry_background": "虚化背景",
    "sunlight": "阳光",
    "day": "明亮日光",
    "night": "夜色",
    "starry_sky": "星空",
    "sunset": "夕阳",
    "dusk": "黄昏",
    "rain": "雨中氛围",
    "blush": "脸红表情",
    "open_mouth": "微张嘴的表情",
    "half-closed_eyes": "半阖眼神",
}


NATURAL_TAG_EN = {
    "city": "an urban city setting",
    "street": "a lively street",
    "indoors": "an interior space",
    "bedroom": "a quiet bedroom",
    "bathroom": "a bathroom",
    "beach": "a seaside beach",
    "ocean": "the ocean in the background",
    "sea": "the sea in the background",
    "water": "near the water",
    "pool": "a swimming pool",
    "poolside": "a poolside setting",
    "school": "a school campus",
    "classroom": "a classroom",
    "forest": "a forest",
    "garden": "a garden",
    "cafe": "a cozy cafe",
    "backpack": "a backpack",
    "camera": "a camera",
    "map": "a map",
    "suitcase": "a suitcase",
    "standing": "standing",
    "sitting": "sitting",
    "walking": "walking",
    "running": "running",
    "swimming": "swimming",
    "sleeping": "sleeping peacefully",
    "lying": "lying down",
    "holding": "holding a prop",
    "holding_cup": "holding a cup",
    "holding_book": "holding a book",
    "fighting": "moving in a combat pose",
    "bathing": "bathing",
    "showering": "showering",
    "nude": "adult nude",
    "kiss": "kissing",
    "full_body": "full-body composition",
    "upper_body": "upper-body composition",
    "cowboy_shot": "cowboy-shot framing",
    "portrait": "portrait framing",
    "looking_at_viewer": "looking at the viewer",
    "dynamic_pose": "dynamic pose",
    "soft_lighting": "soft lighting",
    "cinematic_lighting": "cinematic lighting",
    "depth_of_field": "shallow depth of field",
    "blurry_background": "blurred background",
    "sunlight": "sunlight",
    "day": "clear daylight",
    "night": "night atmosphere",
    "starry_sky": "a starry sky",
    "sunset": "sunset light",
    "dusk": "dusk atmosphere",
    "rain": "rainy atmosphere",
    "blush": "blushing expression",
    "open_mouth": "parted lips",
    "half-closed_eyes": "half-closed eyes",
}


def _tag_to_english_phrase(tag):
    clean = _clean_tag(tag)
    if not clean:
        return "anime character"
    text = re.sub(r"_+", " ", clean)
    text = re.sub(r"\s*\([^)]*\)", "", text).strip()
    return text.title() if text else "anime character"


def _natural_phrase_for_tag(tag, language="zh"):
    clean = _clean_tag(tag)
    if language == "en":
        return NATURAL_TAG_EN.get(clean) or clean.replace("_", " ")
    return NATURAL_TAG_ZH.get(clean) or clean.replace("_", " ")


def _natural_facet_phrase(tags, pool, language="zh", fallback_zh="", fallback_en="", count=2):
    values = []
    for tag in tags or []:
        clean = _clean_tag(tag)
        if clean and clean in pool and clean not in values:
            values.append(clean)
        if len(values) >= count:
            break
    if not values:
        return fallback_en if language == "en" else fallback_zh
    sep = ", " if language == "en" else "、"
    return sep.join(_natural_phrase_for_tag(tag, language=language) for tag in values)


def _natural_prompt_format(target_key, user_prompt):
    key = str(target_key or "").strip().lower()
    if "wan" in key or "video" in key or "umt5" in key:
        return "video_natural"
    if "flux" in key or "t5" in key or key == "flux_t5_en":
        return "natural_en"
    if re.search(r"[\u3400-\u9fff]", str(user_prompt or "")):
        return "natural_zh"
    return "natural_en"


def compose_natural_random_prompt(
    user_prompt,
    source_prompt="",
    target_key="",
    variation_strength=None,
    prompt_variant_seed=None,
    prompt_intent=None,
):
    tag_result = compose_sdxl_random_character_prompt(
        user_prompt,
        source_prompt=source_prompt,
        variation_strength=variation_strength or "rich",
        prompt_variant_seed=prompt_variant_seed,
        prompt_intent=prompt_intent,
    )
    if not tag_result.get("locked"):
        return {"locked": False, "prompt": "", "random": False, "random_intent": tag_result.get("random_intent")}
    prompt_format = _natural_prompt_format(target_key, user_prompt)
    language = "en" if prompt_format == "natural_en" else "zh"
    tags = [
        _clean_tag(item)
        for item in str(tag_result.get("prompt") or "").split(",")
        if _clean_tag(item)
    ]
    composer = dict(tag_result.get("prompt_composer") or {})
    subject = composer.get("subject") if isinstance(composer.get("subject"), dict) else {}
    subject_name = (
        str(subject.get("display_name") or "").strip()
        if language == "en"
        else str(subject.get("display_name_zh") or subject.get("display_name") or "").strip()
    )
    if not subject_name:
        subject_name = "an original anime character" if language == "en" else "原创动漫角色"
    setting = _natural_facet_phrase(tags, SETTING_TAG_POOL, language, "富有层次的场景", "a layered environment")
    action = _natural_facet_phrase(tags, ACTION_TAG_POOL, language, "做出清晰可见的动作", "performing a clear visible action", count=1)
    pose = _natural_facet_phrase(tags, POSE_TAG_POOL, language, "自然稳定的角色姿态", "a natural readable pose", count=1)
    atmosphere = _natural_facet_phrase(tags, ATMOSPHERE_TAG_POOL | EXPRESSION_TAG_POOL, language, "精致光影和明确情绪", "refined lighting and a clear mood")
    adult = bool(tag_result.get("adult"))
    if prompt_format == "video_natural":
        subject_text = f"成人向角色{subject_name}" if adult else f"角色{subject_name}"
        prompt = (
            f"镜头缓慢推进并轻微环绕，{subject_text}在{setting}中{action}，"
            f"始终保持{pose}，背景光影和环境细节随镜头运动逐渐展开，"
            f"{atmosphere}，动作连续自然，画面保持高质量动漫影像风格。"
        )
    elif language == "en":
        subject_text = f"an adult-oriented anime depiction of {subject_name}" if adult else f"an anime character illustration of {subject_name}"
        prompt = (
            f"{subject_text} in {setting}, {action}, with {pose}. "
            f"The composition uses a cinematic camera angle and balanced framing, with {atmosphere}, "
            f"refined lighting, detailed background elements, and a polished high-quality illustration style."
        )
    else:
        subject_text = f"成人向角色{subject_name}" if adult else f"角色{subject_name}"
        prompt = (
            f"{subject_text}出现在{setting}中，正在{action}，呈现{pose}。"
            f"画面采用电影感镜头和稳定构图，{atmosphere}，背景细节丰富，"
            f"光影精致，整体是高质量动漫插画。"
        )
    composer["prompt_format"] = prompt_format
    composer["natural_language"] = language
    return {
        "prompt": prompt,
        "locked": True,
        "random": True,
        "adult": adult,
        "subject_counts": tag_result.get("subject_counts") or {},
        "prompt_intent": tag_result.get("prompt_intent") or {},
        "prompt_composer": composer,
        "tag_prompt_reference": tag_result.get("prompt") or "",
        "random_intent": tag_result.get("random_intent") or {},
        "generation_resolution": tag_result.get("generation_resolution") or {},
    }


def _variation_strength_value(value, intent=None):
    text = str(value or "").strip().lower()
    if text in {"off", "none", "0", "false", "no"}:
        return 0
    if text in {"light", "low", "1"}:
        return 1
    if text in {"rich", "high", "3"}:
        return 3
    if text in {"balanced", "medium", "2"}:
        return 2
    if intent and intent.get("plain_scene"):
        return 0
    if intent and intent.get("detail_scene"):
        return 3
    if intent and intent.get("scene_branch") not in {"", "generic", None}:
        return 2
    return 1


def _frequency_branch_hint_terms(branch, user_prompt=""):
    branch = str(branch or "generic").strip().lower() or "generic"
    hints = list(BRANCH_FREQUENCY_TAG_HINTS.get(branch) or ())
    user_text = str(user_prompt or "").lower()
    for known_branch, branch_hints in BRANCH_FREQUENCY_TAG_HINTS.items():
        if known_branch and known_branch != "generic" and known_branch in user_text:
            _append_unique(hints, branch_hints)
    for token in re.findall(r"[a-z][a-z0-9_]{2,}", user_text):
        if token not in {"the", "and", "with", "for", "girl", "boy", "image", "prompt", "draw"}:
            _append_unique(hints, [token])
    return tuple(hints)


def _filter_frequency_tags_for_branch(tags, branch, user_prompt="", limit=18):
    tags = tuple(tags or ())
    if not tags:
        return ()
    hints = _frequency_branch_hint_terms(branch, user_prompt=user_prompt)
    if not hints:
        return ()
    matched = [tag for tag in tags if _tag_matches_hints(tag, hints)]
    return tuple(matched[:limit])


def _branch_frequency_slot_candidates(branch, limit_per_slot=18, user_prompt=""):
    expanded = _frequency_pool_expansion_data()
    setting = expanded.get("setting") or ()
    return {
        "setting": _filter_frequency_tags_for_branch(setting, branch, user_prompt=user_prompt, limit=limit_per_slot),
        "prop": _filter_frequency_tags_for_branch(setting, branch, user_prompt=user_prompt, limit=max(4, limit_per_slot // 2)),
        "action": _filter_frequency_tags_for_branch(expanded.get("action") or (), branch, user_prompt=user_prompt, limit=limit_per_slot),
        "pose": _filter_frequency_tags_for_branch(expanded.get("pose") or (), branch, user_prompt=user_prompt, limit=limit_per_slot),
        "atmosphere": _filter_frequency_tags_for_branch(expanded.get("atmosphere") or (), branch, user_prompt=user_prompt, limit=limit_per_slot),
        "expression": _filter_frequency_tags_for_branch(expanded.get("expression") or (), branch, user_prompt=user_prompt, limit=limit_per_slot),
    }


def _merged_branch_slot_candidates(branch, user_prompt=""):
    branch = str(branch or "generic").strip().lower() or "generic"
    base = BRANCH_CURATED_SLOT_CANDIDATES.get(branch) or BRANCH_CURATED_SLOT_CANDIDATES.get("generic") or {}
    if branch.startswith("adult_"):
        return {slot: tuple(values or ()) for slot, values in base.items()}
    sfw_extra = _sfw_association_slot_candidates(
        user_prompt,
        scene_tags=_sfw_primary_scene_trigger_tags(user_prompt),
        branch=branch,
        limit_per_facet=18,
    )
    extra = _branch_frequency_slot_candidates(branch, user_prompt=user_prompt)
    merged = {}
    for slot in set(base) | set(extra) | set(sfw_extra):
        values = []
        _append_unique(values, base.get(slot) or ())
        _append_unique(values, sfw_extra.get(slot) or ())
        _append_unique(values, extra.get(slot) or ())
        merged[slot] = tuple(values)
    return merged


def _curated_branch_variant_tags(intent, user_prompt, resolved_tags, copyright_tags, variation_strength=None, variant_seed=None):
    if not intent or intent.get("plain_scene"):
        return []
    strength = _variation_strength_value(variation_strength, intent)
    if strength <= 0:
        return []
    branch = str(intent.get("scene_branch") or "generic").strip().lower() or "generic"
    candidates = _merged_branch_slot_candidates(branch, user_prompt=user_prompt)
    if not candidates:
        return []
    mode = "detailed" if intent.get("detail_scene") else "standard"
    minimums = STORY_FACET_MINIMUMS.get(mode, STORY_FACET_MINIMUMS["standard"])
    current = []
    _append_unique(current, intent.get("scene_tags") or [])
    _append_unique(current, intent.get("composition_tags") or [])
    seed_text = json.dumps(
        {
            "variant_seed": variant_seed,
            "user_prompt": user_prompt,
            "resolved_tags": resolved_tags or [],
            "copyright_tags": copyright_tags or [],
            "branch": branch,
            "strength": strength,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    output = []
    max_total = {1: 3, 2: 5, 3: 8}.get(strength, 5)
    for slot, pool in candidates.items():
        if len(output) >= max_total:
            break
        facet = slot if slot in STORY_FACET_POOLS else "setting" if slot == "prop" else slot
        wanted = 1
        if facet in minimums:
            have = int(_facet_counts(current + output).get(facet) or 0)
            wanted = max(0, int(minimums.get(facet) or 0) - have)
        if wanted <= 0 and strength < 3:
            continue
        if slot == "prop" and strength < 2:
            continue
        for tag in _stable_pick(pool, seed_text + "\n" + slot, max(1, min(wanted or 1, max_total - len(output)))):
            if _semantic_tag_allowed(tag):
                _append_unique(output, [tag])
    return output[:max_total]


SUBJECT_COUNT_WORDS = {
    "0": 0,
    "1": 1,
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "\u4e00": 1,
    "\u4e8c": 2,
    "\u4e24": 2,
    "\u5169": 2,
    "\u4fe9": 2,
    "\u5006": 2,
    "\u4e09": 3,
    "\u56db": 4,
    "\u4e94": 5,
    "\u516d": 6,
}


def _subject_count_word_value(value):
    text = str(value or "").strip().lower()
    if not text:
        return 0
    if text.isdigit():
        return max(0, min(6, int(text)))
    return max(0, min(6, int(SUBJECT_COUNT_WORDS.get(text, 0) or 0)))


def _explicit_subject_mention_counts(text):
    source = str(text or "").lower()
    girls = 0
    boys = 0

    paired_patterns = (
        r"\u4e00\s*(?:\u4e2a|\u500b|\u4f4d|\u540d)?\s*(?:\u7537\u4eba|\u7537\u6027|\u7537\u5b69|\u7537\u751f|\u5c11\u5e74|\u7537\u7684).{0,8}\u4e00\s*(?:\u4e2a|\u500b|\u4f4d|\u540d)?\s*(?:\u5973\u4eba|\u5973\u6027|\u5973\u5b69|\u5973\u751f|\u5c11\u5973|\u5973\u7684)",
        r"\u4e00\s*(?:\u4e2a|\u500b|\u4f4d|\u540d)?\s*(?:\u5973\u4eba|\u5973\u6027|\u5973\u5b69|\u5973\u751f|\u5c11\u5973|\u5973\u7684).{0,8}\u4e00\s*(?:\u4e2a|\u500b|\u4f4d|\u540d)?\s*(?:\u7537\u4eba|\u7537\u6027|\u7537\u5b69|\u7537\u751f|\u5c11\u5e74|\u7537\u7684)",
        r"\b1\s*(?:boy|man|male)\b.{0,8}\b1\s*(?:girl|woman|female)\b",
        r"\b1\s*(?:girl|woman|female)\b.{0,8}\b1\s*(?:boy|man|male)\b",
    )
    if any(re.search(pattern, source, re.I) for pattern in paired_patterns):
        girls = max(girls, 1)
        boys = max(boys, 1)

    count_token = r"(?P<count>\d+|one|two|three|four|five|six|\u4e00|\u4e8c|\u4e24|\u5169|\u4fe9|\u5006|\u4e09|\u56db|\u4e94|\u516d)"
    male_patterns = (
        count_token + r"\s*(?:\u4e2a|\u500b|\u4f4d|\u540d)?\s*(?:\u7537\u4eba|\u7537\u6027|\u7537\u5b69|\u7537\u751f|\u7537\u89d2\u8272|\u5c11\u5e74|\u7537\u7684)",
        count_token + r"\s*(?:boys?|men|males?)\b",
    )
    female_patterns = (
        count_token + r"\s*(?:\u4e2a|\u500b|\u4f4d|\u540d)?\s*(?:\u5973\u4eba|\u5973\u6027|\u5973\u5b69|\u5973\u751f|\u5973\u89d2\u8272|\u5c11\u5973|\u5973\u7684)",
        count_token + r"\s*(?:girls?|women|females?)\b",
    )
    for pattern in male_patterns:
        for match in re.finditer(pattern, source, re.I):
            boys = max(boys, _subject_count_word_value(match.group("count")))
    for pattern in female_patterns:
        for match in re.finditer(pattern, source, re.I):
            girls = max(girls, _subject_count_word_value(match.group("count")))

    return {"girls": girls, "boys": boys}


def _explicit_person_total_count(text):
    source = str(text or "").lower()
    count_token = r"(?P<count>\d+|one|two|three|four|five|six|\u4e00|\u4e8c|\u4e24|\u5169|\u4fe9|\u5006|\u4e09|\u56db|\u4e94|\u516d)"
    patterns = (
        count_token + r"\s*(?:\u4e2a|\u500b|\u4f4d|\u540d)?\s*(?:\u4eba|\u89d2\u8272|\u4e3b\u4f53)",
        count_token + r"\s*(?:people|persons|characters?|subjects?)\b",
    )
    total = 0
    for pattern in patterns:
        for match in re.finditer(pattern, source, re.I):
            total = max(total, _subject_count_word_value(match.group("count")))
    return total


def _subject_count_tags_from_counts(girls, boys):
    output = []
    girls = max(0, min(6, int(girls or 0)))
    boys = max(0, min(6, int(boys or 0)))
    if girls == 1:
        output.append("1girl")
    elif girls > 1:
        output.append(f"{girls}girls")
    if boys == 1:
        output.append("1boy")
    elif boys > 1:
        output.append(f"{boys}boys")
    return output


def _known_character_subject_count_tags(tags):
    girls = 0
    boys = 0
    for tag in tags or ():
        hinted = CHARACTER_SUBJECT_COUNT_HINTS.get(_clean_tag(tag))
        if hinted == "1girl":
            girls += 1
        elif hinted == "1boy":
            boys += 1
    if girls + boys < 2:
        return []
    return _subject_count_tags_from_counts(girls, boys)


def _subject_count_tags(user_prompt, source_prompt, resolved_tags, scene_branch=""):
    lookup = set(resolved_tags or [])
    user_text = str(user_prompt or "").lower()
    source_text = str(source_prompt or "").lower()
    combined = "\n".join(item for item in (user_text, source_text) if item)
    subject_text = user_text if resolved_tags else combined
    explicit_counts = _explicit_subject_mention_counts(subject_text)
    explicit_girls = int(explicit_counts.get("girls") or 0)
    explicit_boys = int(explicit_counts.get("boys") or 0)
    explicit_people = _explicit_person_total_count(subject_text)
    source_explicit_counts = _explicit_subject_mention_counts(source_text)
    source_explicit_girls = int(source_explicit_counts.get("girls") or 0)
    source_explicit_boys = int(source_explicit_counts.get("boys") or 0)
    has_male_mention = bool(re.search(r"\b(1boy|boy|male|man|men)\b|\u7537\u6027|\u7537\u4eba|\u7537\u5b69|\u7537\u751f|\u7537\u89d2\u8272|\u5c11\u5e74|\u5927\u53d4|\u7537\u7c89", subject_text))
    has_female_mention = bool(re.search(r"\b(1girl|girl|female|woman|women)\b|\u5973\u6027|\u5973\u4eba|\u5973\u5b69|\u5973\u751f|\u5973\u89d2\u8272|\u5c11\u5973|\u7f8e\u5973|\u7f8e\u5c11\u5973", subject_text))
    has_passive_external_actor = _has_passive_external_actor_intent(subject_text)
    has_group_other_people = _has_group_other_people_intent(subject_text)
    has_external_others = has_passive_external_actor or has_group_other_people
    has_two_person_correction = bool(re.search(
        r"(?:\u4e0d(?:\u662f|\u8981)?|\u522b|\u4e0d\u6b62).{0,8}(?:\u4e00|\b1\b)\s*(?:\u4e2a|\u500b|\u4f4d|\u540d)?\s*(?:\u4eba|\u89d2\u8272).{0,14}(?:\u4e24|\u5169|\b2\b)\s*(?:\u4e2a|\u500b|\u4f4d|\u540d)?\s*(?:\u4eba|\u89d2\u8272)|(?:\u4e24|\u5169|\b2\b)\s*(?:\u4e2a|\u500b|\u4f4d|\u540d)?\s*(?:\u4eba|\u89d2\u8272)|\u53e6\u4e00\s*(?:\u4e2a|\u500b|\u4f4d|\u540d)?\s*(?:\u4eba|\u89d2\u8272)",
        subject_text,
        re.I,
    ))
    if len(resolved_tags or []) > 1:
        girls = 0
        boys = 0
        for tag in resolved_tags or []:
            hinted = CHARACTER_SUBJECT_COUNT_HINTS.get(tag)
            if hinted == "1girl":
                girls += 1
            elif hinted == "1boy":
                boys += 1
        girls = max(girls, explicit_girls)
        boys = max(boys, explicit_boys)
        if has_male_mention and explicit_boys == 0 and boys == 0:
            boys = 1
        if has_female_mention and explicit_girls == 0 and girls == 0:
            girls = 1
        hinted_total = girls + boys
        if explicit_people and hinted_total and hinted_total < explicit_people:
            missing = explicit_people - hinted_total
            if boys == 0 and not has_male_mention:
                girls += missing
            elif girls == 0 and has_male_mention and not has_female_mention:
                boys += missing
            else:
                girls += missing
            hinted_total = girls + boys
        if hinted_total and hinted_total < len(resolved_tags or []):
            missing = len(resolved_tags or []) - hinted_total
            if boys == 0 and not has_male_mention:
                girls += missing
            elif girls == 0 and has_male_mention and not has_female_mention:
                boys += missing
        source_total = source_explicit_girls + source_explicit_boys
        if not (girls or boys) and source_total == len(resolved_tags or []):
            source_output = _subject_count_tags_from_counts(source_explicit_girls, source_explicit_boys)
            if source_output:
                if has_external_others:
                    _append_unique(source_output, ["multiple_others"])
                return source_output
        explicit_output = _subject_count_tags_from_counts(girls, boys)
        if explicit_output:
            if has_external_others:
                _append_unique(explicit_output, ["multiple_others"])
            return explicit_output
        if girls == 1 and boys == 1:
            return ["1girl", "1boy", "multiple_others"] if has_external_others else ["1girl", "1boy"]
        if girls >= 2 and boys == 0:
            output = [f"{min(girls, 6)}girls"]
            if has_external_others:
                _append_unique(output, ["multiple_others"])
            return output
        if boys >= 2 and girls == 0:
            output = [f"{min(boys, 6)}boys"]
            if has_external_others:
                _append_unique(output, ["multiple_others"])
            return output
        if not has_male_mention:
            output = [f"{min(len(resolved_tags or []), 6)}girls"]
            if has_external_others:
                _append_unique(output, ["multiple_others"])
            return output
        return ["multiple_others"]
    if str(scene_branch or "").strip().lower() == "romance" and has_external_others:
        for tag in resolved_tags or []:
            hinted = CHARACTER_SUBJECT_COUNT_HINTS.get(tag)
            if hinted in {"1girl", "1boy"}:
                return [hinted, "multiple_others"]
        return ["1girl", "multiple_others"]
    if str(scene_branch or "").strip().lower() == "romance":
        for tag in resolved_tags or []:
            hinted = CHARACTER_SUBJECT_COUNT_HINTS.get(tag)
            if hinted == "1boy":
                return ["1boy", "1girl"]
            if hinted == "1girl":
                return ["1girl", "1boy"]
        return ["1girl", "1boy"]
    for tag in resolved_tags or []:
        hinted = CHARACTER_SUBJECT_COUNT_HINTS.get(tag)
        if explicit_girls or explicit_boys:
            girls = explicit_girls
            boys = explicit_boys
            if hinted == "1girl":
                girls = max(girls, 1)
            elif hinted == "1boy":
                boys = max(boys, 1)
            explicit_output = _subject_count_tags_from_counts(girls, boys)
            if explicit_output:
                if has_passive_external_actor:
                    _append_unique(explicit_output, ["multiple_others"])
                return explicit_output
        if hinted == "1girl" and has_male_mention:
            return ["1girl", "1boy"]
        if hinted == "1boy" and has_female_mention:
            return ["1boy", "1girl"]
        if hinted in {"1girl", "1boy"} and has_external_others:
            return [hinted, "multiple_others"]
        if hinted == "1girl" and has_two_person_correction:
            return ["1girl", "1boy"] if has_male_mention else ["2girls"]
        if hinted == "1boy" and has_two_person_correction:
            return ["1boy", "1girl"] if has_female_mention else ["2boys"]
        if hinted:
            return [hinted]
    explicit_output = _subject_count_tags_from_counts(explicit_girls, explicit_boys)
    if explicit_output:
        if has_external_others:
            _append_unique(explicit_output, ["multiple_others"])
        return explicit_output
    if has_male_mention:
        return ["1boy", "multiple_others"] if has_external_others else ["1boy"]
    if has_female_mention:
        return ["1girl", "multiple_others"] if has_external_others else ["1girl"]
    if any(tag in lookup for tag in ("genshin_impact", "fate/stay_night", "fate_(series)", "vocaloid")):
        return ["1girl", "multiple_others"] if has_external_others else ["1girl"]
    return ["1girl", "multiple_others"] if has_external_others else ["1girl"]


def _subject_count_implies_multiple(tags):
    tag_set = set(tags or [])
    return bool(
        ("1girl" in tag_set and "1boy" in tag_set)
        or tag_set.intersection({"2girls", "2boys", "multiple_others"})
    )


def plan_prompt_intent(user_prompt, source_prompt="", resolution=None):
    scene_user_prompt = _character_name_masked_text(user_prompt, resolution)
    scene_source_prompt = _character_name_masked_text(source_prompt, resolution)
    combined = "\n".join(item for item in (str(scene_user_prompt or ""), str(scene_source_prompt or "")) if item)
    composition_tags = _rule_tags(user_prompt, COMPOSITION_RULES)
    plain_scene = _has_plain_scene_intent(combined)
    detail_scene = bool(not plain_scene and _has_detail_scene_intent(combined))
    scene_tags = _rule_tags(scene_user_prompt, PLAIN_SCENE_RULES if plain_scene else SCENE_RULES)
    if plain_scene:
        _append_unique(scene_tags, _rule_tags(scene_user_prompt, PLAIN_SCENE_CARRY_RULES))
    if not plain_scene:
        _append_unique(scene_tags, _rule_tags(scene_user_prompt, ADULT_SCENE_RULES))
    if not plain_scene:
        _append_unique(scene_tags, _semantic_candidate_tags(scene_user_prompt, scene_source_prompt))
    user_scene_branch = _scene_intent_branch(scene_user_prompt)
    has_passive_external_actor = _has_passive_external_actor_intent(combined)
    semantic_interaction_branch = "" if has_passive_external_actor else ("romance" if set(scene_tags).intersection(INTERACTION_LOCK_TAGS) else "")
    scene_branch = "" if plain_scene else (user_scene_branch or semantic_interaction_branch or ("" if scene_tags else _scene_intent_branch(scene_source_prompt)) or "generic")
    scene_mode = "plain" if plain_scene else "detailed" if detail_scene else "standard"
    return {
        "composition_tags": composition_tags,
        "scene_tags": scene_tags,
        "scene_branch": scene_branch,
        "detail_scene": detail_scene,
        "plain_scene": plain_scene,
        "scene_mode": scene_mode,
        "scene_minimum": 0 if plain_scene else 8 if detail_scene else 5,
    }


def _apply_user_explicit_conflict_filters(tags, intent):
    output = list(tags or [])
    explicit_scene_tags = set((intent or {}).get("scene_tags") or [])
    output = _apply_selfie_scene_filters(output, intent)
    if "day" in explicit_scene_tags:
        output = [
            tag for tag in output
            if tag not in {"night", "moonlight", "night_sky", "starry_sky", "full_moon", "sunset", "evening", "dusk"}
        ]
    branch = str((intent or {}).get("scene_branch") or "").strip().lower()
    if "kiss" in explicit_scene_tags or branch == "kiss":
        output = [
            tag for tag in output
            if tag not in {
                "looking_at_viewer", "facing_viewer", "smile", "closed_mouth_smile",
                "dynamic_pose", "standing", "walking", "running", "jumping",
                "holding_flower", "holding_camera", "casting_spell",
                "reaching_towards_viewer", "from_below", "paper_lantern", "lantern",
            }
        ]
    if "sleeping" in explicit_scene_tags or branch == "sleep":
        output = [
            tag for tag in output
            if tag not in {
                "looking_at_viewer", "facing_viewer", "smile", "closed_mouth_smile",
                "dynamic_pose", "standing", "sitting", "walking", "running",
                "jumping", "holding_flower", "holding_camera", "casting_spell",
                "reaching_towards_viewer", "from_below",
            }
        ]
    defeated_tags = {
        "lying", "on_ground", "injury", "rolling_eyes", "white_eyes",
        "empty_eyes", "torn_clothes", "kneeling",
    }
    if explicit_scene_tags.intersection(defeated_tags):
        blocked = {
            "looking_at_viewer", "facing_viewer", "smile",
            "closed_mouth_smile", "gentle_smile", "light_smile",
            "standing", "walking", "running", "jumping", "sitting",
            "dynamic_pose", "reaching_towards_viewer", "from_below",
            "casting_spell", "pyrokinesis", "magic", "magic_circle",
            "fire", "embers", "sparks", "holding_hands", "hug",
            "holding_flower", "holding_camera",
        }
        context_blocked = {
            "looking_back", "umbrella", "holding_umbrella", "sunset",
            "evening", "backlighting", "city", "street", "casual",
        }
        output = [
            tag for tag in output
            if tag not in blocked and not (tag in context_blocked and tag not in explicit_scene_tags)
        ]
    attacked_tags = {"hitting", "punching", "slapping"}
    if explicit_scene_tags.intersection(attacked_tags):
        output = [
            tag for tag in output
            if tag not in {
                "looking_at_viewer", "facing_viewer", "smile",
                "closed_mouth_smile", "gentle_smile", "light_smile",
                "solo", "standing", "walking", "sitting",
                "holding_flower", "holding_camera", "holding_hands",
                "hug", "eating", "feeding", "sharing_food",
            }
        ]
    if explicit_scene_tags.intersection(INTERACTION_LOCK_TAGS):
        output = [
            tag for tag in output
            if tag not in {"looking_at_viewer", "facing_viewer"}
        ]
    if not explicit_scene_tags.intersection({"lap_pillow", "sitting_on_lap", "sitting_on_person"}):
        output = [
            tag for tag in output
            if tag not in {"sitting_on_lap", "sitting_on_person"}
        ]
    if "multiple_others" in set(output) and (branch == "group_play" or "playing" in explicit_scene_tags or "looking_at_another" in set(output)):
        output = [
            tag for tag in output
            if tag not in {"solo", "looking_at_viewer", "facing_viewer"}
        ]
    if explicit_scene_tags.intersection({"profile", "from_side", "looking_to_the_side"}) or set(output).intersection({"profile", "from_side", "looking_to_the_side"}):
        output = [
            tag for tag in output
            if tag not in {"looking_at_viewer", "facing_viewer"}
        ]
    return output


ADULT_PANTIES_TAGS = {
    "panties", "wet_panties", "white_panties", "black_panties",
    "striped_panties", "lace-trimmed_panties", "string_panties",
    "panties_around_one_leg", "panties_removed",
}

ADULT_NO_PANTIES_TAGS = {"no_panties"}

ADULT_SPECIFIC_POSITION_TAGS = {
    "cowgirl_position", "reverse_cowgirl", "girl_on_top", "missionary",
    "doggystyle", "sex_from_behind", "straddling", "upright_straddle",
    "full_nelson", "mating_press",
}

ADULT_ORAL_FOCUS_TAGS = {
    "oral/fellatio", "fellatio", "deepthroat", "irrumatio",
    "licking_penis", "penis_on_face", "cum_in_mouth",
}

ADULT_FACE_CUM_FOCUS_TAGS = {
    "facial", "bukkake",
}

ADULT_ORAL_OFF_FOCUS_TAGS = {
    "pussy", "pussy/vaginal", "vaginal", "cum_in_pussy",
    "pussy_juice", "pussy_juice_stain", "pov_crotch",
    "ass", "spread_legs", "spread_ass", "spread_anus",
    "doggystyle", "cowgirl_position",
    "reverse_cowgirl", "missionary", "sex_from_behind",
    "standing", "walking",
}


def _apply_adult_conflict_filters(tags, adult_tags=None, explicit_full_body=False):
    output = list(tags or [])
    tag_set = set(output)
    adult_tag_set = set(adult_tags or ())
    if tag_set.intersection(ADULT_PANTIES_TAGS) and tag_set.intersection(ADULT_NO_PANTIES_TAGS):
        if adult_tag_set.intersection(ADULT_NO_PANTIES_TAGS):
            output = [tag for tag in output if tag not in ADULT_PANTIES_TAGS]
        else:
            output = [tag for tag in output if tag not in ADULT_NO_PANTIES_TAGS]
        tag_set = set(output)
    if tag_set.intersection(ADULT_NO_PANTIES_TAGS) and any("swimsuit" in str(tag or "") or "bikini" in str(tag or "") for tag in tag_set):
        if adult_tag_set.intersection(ADULT_NO_PANTIES_TAGS):
            output = [
                tag for tag in output
                if "swimsuit" not in str(tag or "") and "bikini" not in str(tag or "")
            ]
        else:
            output = [tag for tag in output if tag not in ADULT_NO_PANTIES_TAGS]
        tag_set = set(output)
    if tag_set.intersection(ADULT_SPECIFIC_POSITION_TAGS):
        blocked_pose = {"sitting", "standing", "walking"}
        if not explicit_full_body:
            blocked_pose.add("full_body")
        if tag_set.intersection({"cowgirl_position", "reverse_cowgirl", "girl_on_top", "straddling", "upright_straddle"}):
            blocked_pose.add("lying")
        output = [tag for tag in output if tag not in blocked_pose]
        tag_set = set(output)
    if "sex" in tag_set:
        if tag_set.intersection({"solo", "1girl", "1boy"}):
            output = [tag for tag in output if tag not in {"yuri", "yaoi"}]
            tag_set = set(output)
        output = [tag for tag in output if tag != "from_below"]
        tag_set = set(output)
    if "ass_grab" in tag_set and tag_set.intersection({"spread_legs", "on_back"}):
        if "ass_grab" in adult_tag_set:
            output = [tag for tag in output if tag not in {"spread_legs", "on_back"}]
        else:
            output = [tag for tag in output if tag != "ass_grab"]
        tag_set = set(output)
    if tag_set.intersection({"breast_grab", "nipple_tweak"}):
        output = [tag for tag in output if tag != "ass"]
        tag_set = set(output)
    if tag_set.intersection(ADULT_ORAL_FOCUS_TAGS):
        output = [
            tag for tag in output
            if tag not in ADULT_ORAL_OFF_FOCUS_TAGS
            and not (tag == "licking" and "licking_penis" not in tag_set)
        ]
        tag_set = set(output)
    if "nude" in tag_set:
        output = [
            tag for tag in output
            if "swimsuit" not in str(tag or "") and tag not in {"bikini", "bikini_top", "bikini_bottom"}
        ]
        tag_set = set(output)
    if tag_set.intersection({"bathroom", "bathing", "showering", "bathtub", "shower_head", "onsen"}):
        output = [
            tag for tag in output
            if tag not in {
                "bedroom", "bed", "on_bed", "pillow", "blanket",
                "window", "curtains", "table", "desk", "sitting", "holding", "sunlight",
            }
        ]
    if "nude" in tag_set and "full_body" in tag_set:
        output = [tag for tag in output if tag != "close-up"]
    return output


def _apply_adult_negative_conflict_filters(
    tags,
    adult_tags=None,
    explicit_tags=None,
    preferred_tags=None,
    min_score=ADULT_FINAL_NEGATIVE_MIN_SCORE,
    max_lift=ADULT_FINAL_NEGATIVE_MAX_LIFT,
    return_removed=False,
):
    output = []
    removed = []
    adult_explicit = {_clean_tag(tag) for tag in adult_tags or () if _clean_tag(tag)}
    explicit = {_clean_tag(tag) for tag in explicit_tags or () if _clean_tag(tag)}
    preferred = {_clean_tag(tag) for tag in preferred_tags or () if _clean_tag(tag)}

    def priority(tag):
        if tag in adult_explicit:
            return 4
        if tag in explicit:
            return 3
        if tag in preferred:
            return 2
        return 1

    for tag in tags or ():
        clean = _clean_tag(tag)
        if not clean:
            continue
        conflict_index = None
        conflict_row = None
        for index, existing in enumerate(output):
            row = _adult_negative_conflict_row(existing, clean)
            if not row:
                continue
            if (
                float(row.get("negative_score") or 0.0) >= float(min_score or 0.0)
                and float(row.get("lift") or 1.0) <= float(max_lift or 1.0)
            ):
                conflict_index = index
                conflict_row = row
                break
        if conflict_index is None:
            _append_unique(output, [clean])
            continue
        existing = output[conflict_index]
        if priority(clean) > priority(existing):
            removed.append({
                "kept": clean,
                "removed": existing,
                "negative_score": round(float((conflict_row or {}).get("negative_score") or 0.0), 3),
            })
            output.pop(conflict_index)
            _append_unique(output, [clean])
        else:
            removed.append({
                "kept": existing,
                "removed": clean,
                "negative_score": round(float((conflict_row or {}).get("negative_score") or 0.0), 3),
            })
    if return_removed:
        return output, removed
    return output


def _apply_bathing_scene_conflict_filters(tags, intent=None):
    output = list(tags or [])
    explicit_scene_tags = set((intent or {}).get("scene_tags") or [])
    tag_set = set(output)
    if not explicit_scene_tags.intersection({"bathroom", "bathing", "showering", "bathtub", "shower_head"}):
        return output
    return [
        tag for tag in output
        if tag not in {
            "outdoors", "shrine", "torii", "paper_lantern", "lantern", "night", "moonlight",
            "butterfly", "fire", "pyrokinesis", "holding_flower", "reaching_towards_viewer",
            "dynamic_pose", "smile", "window", "curtains", "table", "desk", "teacup", "tea",
            "cup", "holding_cup", "drinking", "book", "holding_book", "reading", "office",
            "paper", "papers", "holding_pen", "writing", "bedroom", "bed", "on_bed", "pillow",
            "blanket", "sitting", "standing", "walking", "sunlight", "backlighting",
        }
    ]


def _apply_indoor_scene_conflict_filters(tags, intent=None):
    output = list(tags or [])
    explicit_scene_tags = set((intent or {}).get("scene_tags") or [])
    indoor_tags = {
        "indoors", "classroom", "kindergarten", "office", "library", "cafe", "teahouse",
        "bedroom", "bathroom", "kitchen", "bar", "restaurant", "living_room",
        "hallway", "corridor", "dojo", "music_room",
    }
    if not explicit_scene_tags.intersection(indoor_tags):
        return output
    return [
        tag for tag in output
        if tag not in {
            "outdoors", "sky", "cloud", "clouds", "blue_sky", "cloudy_sky",
            "grass", "meadow", "forest", "park", "garden", "mountain",
            "hills", "shrine", "torii", "paper_lantern", "lantern",
            "beach", "ocean", "sea", "holding_flower", "flower",
        }
    ]


def _apply_bed_scene_conflict_filters(tags, intent=None):
    output = list(tags or [])
    explicit_scene_tags = set((intent or {}).get("scene_tags") or [])
    tag_set = set(output)
    if not (explicit_scene_tags.intersection({"bedroom", "bed", "on_bed"}) or tag_set.intersection({"bedroom", "bed", "on_bed"})):
        return output
    return [
        tag for tag in output
        if tag not in {
            "outdoors", "sky", "cloud", "clouds", "blue_sky", "cloudy_sky",
            "city", "street", "road", "alley", "beach", "ocean", "sea",
            "forest", "park", "garden", "grass", "mountain", "hills",
            "shrine", "torii", "paper_lantern", "lantern",
        }
    ]


def _apply_beach_scene_conflict_filters(tags, intent=None):
    output = list(tags or [])
    explicit_scene_tags = set((intent or {}).get("scene_tags") or [])
    tag_set = set(output)
    if not (explicit_scene_tags.intersection({"beach", "ocean"}) or tag_set.intersection({"beach", "ocean"})):
        return output
    conflict_tags = {
        "indoors", "classroom", "kindergarten", "office", "library", "cafe", "teahouse",
        "bedroom", "bed", "on_bed", "pillow", "blanket", "window", "curtains",
        "table", "desk", "paper", "papers", "holding_pen", "writing", "book",
        "holding_book", "reading", "teacup", "tea", "cup", "holding_cup",
        "drinking", "shrine", "torii", "paper_lantern", "lantern",
    }
    if explicit_scene_tags.intersection({"playing"}) or "playing" in tag_set:
        conflict_tags.update({"holding", "sitting"})
    return [
        tag for tag in output
        if tag not in conflict_tags
    ]


def _apply_street_scene_conflict_filters(tags, intent=None):
    output = list(tags or [])
    explicit_scene_tags = set((intent or {}).get("scene_tags") or [])
    tag_set = set(output)
    if not (explicit_scene_tags.intersection({"city", "street"}) or tag_set.intersection({"city", "street"})):
        return output
    conflict_tags = {
        "indoors", "classroom", "kindergarten", "office", "library", "teahouse", "bedroom",
        "bed", "on_bed", "pillow", "blanket", "window", "curtains", "desk",
        "table", "paper", "papers", "holding_pen", "writing", "book", "holding_book",
        "reading", "teacup", "tea", "cup", "holding_cup", "drinking",
    }
    if tag_set.intersection({"bar", "alcohol", "holding_glass"}):
        conflict_tags.discard("drinking")
    return [
        tag for tag in output
        if tag not in conflict_tags
    ]


def _apply_major_scene_conflict_filters(tags, intent=None):
    output = [str(tag or "").strip() for tag in (tags or []) if str(tag or "").strip()]
    if not output:
        return []
    tag_set = set(output)
    explicit_scene_tags = {str(tag or "").strip() for tag in (intent or {}).get("scene_tags") or [] if str(tag or "").strip()}
    pool_tags = {"pool", "poolside", "lifebuoy", "holding_swim_ring", "swimming"}
    if tag_set.intersection(pool_tags) or explicit_scene_tags.intersection(pool_tags):
        blocked = {"beach", "ocean", "sea", "sand", "wave", "waves", "horizon", "table", "desk"}
        return [tag for tag in output if tag not in blocked]
    if "lake" in tag_set and tag_set.intersection({"mountain", "mountains", "hills"}):
        return output
    groups = (
        ("beach_ocean", {"beach", "ocean", "sea", "sand", "wave", "waves", "horizon"}),
        ("city_street", {"city", "street", "road", "alley", "shopping", "shop", "urban", "crosswalk", "building", "buildings"}),
        ("forest_garden", {"forest", "garden", "park", "grass", "flower", "flowers", "plant", "plants", "tree", "trees", "meadow", "field"}),
        ("indoors_room", {"indoors", "bedroom", "classroom", "kindergarten", "library", "office", "bathroom", "living_room", "kitchen", "cafe", "restaurant", "hallway", "corridor"}),
    )
    preferred_group = None
    for name, members in groups:
        if explicit_scene_tags.intersection(members):
            preferred_group = name
            break
    if not preferred_group:
        for tag in output:
            for name, members in groups:
                if tag in members:
                    preferred_group = name
                    break
            if preferred_group:
                break
    if not preferred_group:
        return output
    removable = set()
    for name, members in groups:
        if name != preferred_group:
            removable.update(members)
    filtered = [tag for tag in output if tag not in removable]
    return filtered or output


def _apply_explicit_visual_bias_filters(tags, user_prompt="", source_prompt=""):
    output = [str(tag or "").strip() for tag in (tags or []) if str(tag or "").strip()]
    combined_text = f"{str(user_prompt or '')}\n{str(source_prompt or '')}"
    explicit_patterns = {
        "soft_lighting": r"\u67d4\u5149|\u67d4\u548c\u5149|\u67d4\u7f8e\u5149|\bsoft\s+lighting\b",
        "sunlight": r"\u9633\u5149|\u65e5\u5149|\u65e5\u7167|\u5149\u7ebf|\bsunlight\b|\bdaylight\b",
        "light_rays": r"\u5149\u675f|\u8036\u7a23\u5149|\u4e01\u8fbe\u5c14|\blight\s+rays?\b|\bgod\s+rays?\b",
        "depth_of_field": r"\u666f\u6df1|\u6df1\u666f\u6df1|\bdepth\s+of\s+field\b|\bdof\b",
        "blurry_background": r"\u80cc\u666f\u865a\u5316|\u80cc\u666f\u6a21\u7cca|\u865a\u5316\u80cc\u666f|\bblur(?:red|ry)?\s+background\b|\bbokeh\b",
        "backlighting": r"\u9006\u5149|\u80cc\u5149|\bbacklight(?:ing)?\b",
    }
    keep = set()
    for tag, pattern in explicit_patterns.items():
        if re.search(pattern, combined_text, re.I):
            keep.add(tag)
    return [tag for tag in output if tag not in explicit_patterns or tag in keep]


def normalize_structured_prompt_intent(prompt_intent):
    if not isinstance(prompt_intent, dict):
        return {}
    output = {}
    scene_strictness = str(prompt_intent.get("scene_strictness") or "").strip().lower()
    if scene_strictness in {"low", "medium", "high", "draft"}:
        output["scene_strictness"] = scene_strictness
    if prompt_intent.get("draft_first") or prompt_intent.get("llm_draft_first"):
        output["draft_first"] = True
    intent_hints = []
    for item in prompt_intent.get("intent_hints") or ():
        text = str(item or "").strip()
        if text and text not in intent_hints:
            intent_hints.append(text[:120])
    if intent_hints:
        output["intent_hints"] = intent_hints[:12]
    if "interaction_focus" in prompt_intent:
        output["interaction_focus"] = bool(prompt_intent.get("interaction_focus"))
    primary_relation = str(prompt_intent.get("primary_relation") or "").strip().lower()
    if primary_relation:
        output["primary_relation"] = primary_relation[:80]
    locked_tags = []
    for item in prompt_intent.get("locked_tags") or ():
        clean = _clean_tag(item)
        if clean and clean not in locked_tags:
            locked_tags.append(clean)
    must_preserve = []
    for item in prompt_intent.get("must_preserve") or ():
        text = str(item or "").strip()
        if text and text not in must_preserve:
            must_preserve.append(text[:120])
        clean = _clean_structured_prompt_enrichment_tag(text)
        if clean and clean not in locked_tags:
            locked_tags.append(clean)
    if locked_tags:
        output["locked_tags"] = locked_tags[:20]
    if must_preserve:
        output["must_preserve"] = must_preserve[:12]
    enrichment_tags = []
    for item in _structured_prompt_intent_enrichment_candidates(prompt_intent):
        clean = _clean_structured_prompt_enrichment_tag(item)
        if clean and clean not in locked_tags and clean not in enrichment_tags:
            enrichment_tags.append(clean)
    if enrichment_tags:
        output["enrichment_tags"] = enrichment_tags[:16 if output.get("draft_first") else 12]
    return output


def _structured_prompt_intent_enrichment_candidates(prompt_intent):
    if not isinstance(prompt_intent, dict):
        return []
    keys = (
        "enrichment_tags",
        "suggested_tags",
        "candidate_tags",
        "style_tags",
        "composition_tags",
        "pose_tags",
        "expression_tags",
        "lighting_tags",
        "atmosphere_tags",
        "camera_tags",
        "setting_tags",
        "prop_tags",
        "action_tags",
    )
    containers = [prompt_intent]
    for nested_key in ("enrichment_slots", "slots", "tag_slots", "visual_slots"):
        nested = prompt_intent.get(nested_key)
        if isinstance(nested, dict):
            containers.append(nested)
    output = []
    for container in containers:
        for key in keys:
            value = container.get(key)
            if isinstance(value, str):
                output.extend(part.strip() for part in value.split(","))
            elif isinstance(value, (list, tuple)):
                output.extend(value)
    return output


def _clean_structured_prompt_enrichment_tag(tag):
    clean = _clean_tag(tag)
    clean = canvas_danbooru_policy.REPAIR_TAG_ALIASES.get(clean, clean)
    if not clean:
        return ""
    if clean in {
        "1girl", "2girls", "3girls", "4girls", "5girls", "6girls",
        "1boy", "2boys", "3boys", "4boys", "5boys", "6boys",
        "solo", "multiple_others", "no_humans",
    }:
        return ""
    if clean in canvas_danbooru_policy.QUALITY_TAGS or clean in PLAIN_OUTPUT_TAGS:
        return ""
    if canvas_danbooru_policy.is_named_character_leak_tag(clean):
        return ""
    if clean in LLM_DRAFT_LOCAL_REPAIR_TAGS:
        return clean
    if canvas_danbooru_policy.is_named_character_default_detail_tag(clean):
        return ""
    if clean.count("_") >= 4 and clean not in SCENE_TAG_POOL:
        return ""
    allowed = set().union(
        SCENE_TAG_POOL,
        SETTING_TAG_POOL,
        ACTION_TAG_POOL,
        POSE_TAG_POOL,
        ATMOSPHERE_TAG_POOL,
        EXPRESSION_TAG_POOL,
        SOURCE_STYLE_CARRYOVER_TAGS,
        set(_danbooru_general_tag_lookup().values()),
    )
    if clean not in allowed:
        return ""
    if not _semantic_tag_allowed(clean):
        return ""
    return clean


def structured_prompt_intent_locked_tags(prompt_intent):
    return list(normalize_structured_prompt_intent(prompt_intent).get("locked_tags") or [])


def structured_prompt_intent_is_strict(prompt_intent):
    intent = normalize_structured_prompt_intent(prompt_intent)
    if str(intent.get("scene_strictness") or "") == "high":
        return True
    if intent.get("interaction_focus") and intent.get("locked_tags"):
        return True
    return False


def compose_sdxl_named_character_prompt(user_prompt, source_prompt="", resolution=None, variation_strength=None, prompt_variant_seed=None, prompt_intent=None):
    resolution = resolution or canvas_danbooru_service._canvas_requested_character_resolution(user_prompt, source_prompt)
    resolved_tags, copyright_tags = _expanded_identity_tags(user_prompt, source_prompt, resolution)
    structured_prompt_intent = normalize_structured_prompt_intent(prompt_intent)
    locked_tags = structured_prompt_intent.get("locked_tags") or []
    if _blue_archive_student_request_text(user_prompt, source_prompt):
        locked_tags = [tag for tag in locked_tags if tag != "solo"]
    strict_prompt_intent = structured_prompt_intent_is_strict(structured_prompt_intent)
    draft_first_prompt_intent = bool(
        structured_prompt_intent.get("draft_first")
        or str(structured_prompt_intent.get("scene_strictness") or "") == "draft"
    )
    adult_intent = detect_adult_intent(user_prompt, source_prompt)
    if adult_intent.get("is_adult"):
        adult_composed = compose_sdxl_adult_named_character_prompt(
            user_prompt,
            source_prompt,
            resolution=resolution,
            variation_strength=variation_strength,
            prompt_variant_seed=prompt_variant_seed,
        )
        if adult_composed.get("locked") or adult_composed.get("state") == "blocked":
            return adult_composed
    intent = plan_prompt_intent(user_prompt, source_prompt, resolution=resolution)
    if not resolved_tags:
        repaired_prompt = canvas_danbooru_policy.repair_tag_list(
            source_prompt,
            resolved_tags=resolved_tags,
            copyright_tags=copyright_tags,
            unknown_tags=canvas_danbooru_service._canvas_unknown_character_like_prompt_tags(source_prompt),
        )
        repaired_tags = [_clean_tag(raw) for raw in str(repaired_prompt or "").split(",")]
        repaired_tags = [tag for tag in repaired_tags if tag]
        repaired_count_tags = _known_character_subject_count_tags(repaired_tags)
        if repaired_count_tags:
            repaired_tags = _sanitize_final_canonical_tags(
                repaired_tags,
                user_prompt,
                source_prompt=source_prompt,
                resolved_tags=[],
                copyright_tags=[],
                intent=intent,
                subject_count_tags=repaired_count_tags,
            )
            repaired_prompt = _prompt_text_from_tags(repaired_tags, user_prompt, source_prompt=source_prompt, variation_strength=variation_strength)
        return {
            "prompt": repaired_prompt,
            "locked": False,
            "intent": intent,
            "resolution": resolution,
        }

    output = []
    subject_count_tags = _subject_count_tags(user_prompt, source_prompt, resolved_tags, intent.get("scene_branch"))
    _append_unique(output, subject_count_tags)
    if (
        str(intent.get("scene_branch") or "") not in {"romance", "kiss"}
        and len(resolved_tags) <= 1
        and not _subject_count_implies_multiple(subject_count_tags)
    ):
        _append_unique(output, ["solo"])
    _append_unique(output, resolved_tags)
    _append_unique(output, copyright_tags)
    if "2girls" in subject_count_tags and str(intent.get("scene_branch") or "") == "kiss":
        _append_unique(output, ["yuri"])
    _append_unique(output, intent["composition_tags"])
    _append_unique(output, locked_tags)

    if "upper_body" in output:
        output = [tag for tag in output if tag != "full_body"]

    source_identity_tags = set(canvas_danbooru_service._canvas_known_identity_prompt_tags(source_prompt))
    trusted_identity_tags = set(resolved_tags or []) | set(copyright_tags or [])
    source_has_untrusted_identity = bool(source_identity_tags and not source_identity_tags.issubset(trusted_identity_tags))
    source_tags = [] if intent["plain_scene"] or source_has_untrusted_identity else _source_safe_tags(source_prompt, include_scene=False)
    source_scene_tags = []
    source_tags = [tag for tag in source_tags if tag not in {"1girl", "1boy"} or tag in subject_count_tags]
    branch_forbidden = SOURCE_BRANCH_FORBIDDEN_TAGS.get(str(intent.get("scene_branch") or "").strip().lower()) or set()
    if branch_forbidden:
        source_tags = [tag for tag in source_tags if tag not in branch_forbidden]
        source_scene_tags = [tag for tag in source_scene_tags if tag not in branch_forbidden]
    if "upper_body" in output:
        source_tags = [tag for tag in source_tags if tag != "full_body"]
        source_scene_tags = [tag for tag in source_scene_tags if tag != "full_body"]
    _append_unique(output, source_tags)
    structured_enrichment_tags = list(structured_prompt_intent.get("enrichment_tags") or [])
    accepted_enrichment_tags = structured_enrichment_tags if draft_first_prompt_intent else ([] if strict_prompt_intent else structured_enrichment_tags)
    _append_unique(output, accepted_enrichment_tags)

    explicit_scene = list(intent["scene_tags"])
    _append_unique(output, explicit_scene)
    if not intent["plain_scene"]:
        branch = str(intent.get("scene_branch") or "").strip().lower()
        has_locked_interaction = bool(set(explicit_scene).intersection(PROFILE_LOCK_TAGS))
        has_defeated_state = _intent_has_defeated_state(intent)
        profile_tags = []
        if not strict_prompt_intent and not draft_first_prompt_intent and _needs_story_enrichment(output, intent) and not (branch == "romance" and has_locked_interaction):
            profile_tags = _intent_profile_tags(intent)
        if profile_tags:
            _append_unique(output, profile_tags)
        variant_tags = [] if strict_prompt_intent or draft_first_prompt_intent or has_defeated_state or (branch == "romance" and has_locked_interaction) else _curated_branch_variant_tags(
            intent,
            user_prompt,
            resolved_tags,
            copyright_tags,
            variation_strength=variation_strength,
            variant_seed=prompt_variant_seed,
        )
        _append_unique(output, variant_tags)
        _append_unique(profile_tags, variant_tags)
        if not strict_prompt_intent and not draft_first_prompt_intent and not profile_tags:
            if explicit_scene:
                if has_locked_interaction:
                    fallback = GENERIC_INTERACTION_SCENE_TAGS
                else:
                    fallback = GENERIC_DETAILED_SCENE_TAGS if intent["detail_scene"] else GENERIC_STANDARD_SCENE_TAGS
                profile_tags = list(explicit_scene) + list(fallback)
            elif source_scene_tags:
                _append_unique(output, source_scene_tags)
                profile_tags = list(source_scene_tags) + list(GENERIC_DETAILED_SCENE_TAGS if intent["detail_scene"] else GENERIC_STANDARD_SCENE_TAGS)
            else:
                profile_tags = _detail_profile_tags(resolved_tags, copyright_tags) if intent["detail_scene"] else _standard_profile_tags(resolved_tags, copyright_tags)
        if not strict_prompt_intent:
            if not draft_first_prompt_intent:
                _ensure_story_facets(output, profile_tags, intent)

    if (
        not any(tag in output for tag in ("upper_body", "portrait", "cowboy_shot", "close-up", "full_body"))
        and str(intent.get("scene_branch") or "").strip().lower() not in {"sleep", "kiss"}
        and not _subject_count_implies_multiple(subject_count_tags)
        and not structured_prompt_intent.get("interaction_focus")
        and not draft_first_prompt_intent
    ):
        _append_unique(output, ["looking_at_viewer"])
    output = _apply_user_explicit_conflict_filters(output, intent)
    output = _apply_indoor_scene_conflict_filters(output, intent)
    output = _apply_bathing_scene_conflict_filters(output, intent)
    output = _apply_bed_scene_conflict_filters(output, intent)
    output = _apply_beach_scene_conflict_filters(output, intent)
    output = _apply_street_scene_conflict_filters(output, intent)
    output = _apply_major_scene_conflict_filters(output, intent)
    output = _apply_explicit_visual_bias_filters(output, user_prompt, source_prompt)
    _append_unique(output, getattr(canvas_danbooru_policy, "NAMED_CHARACTER_DEFAULT_PROMPT_TAGS", ()))
    output = _apply_user_explicit_conflict_filters(output, intent)
    output = _apply_indoor_scene_conflict_filters(output, intent)
    output = _apply_bathing_scene_conflict_filters(output, intent)
    output = _apply_bed_scene_conflict_filters(output, intent)
    output = _apply_beach_scene_conflict_filters(output, intent)
    output = _apply_street_scene_conflict_filters(output, intent)
    output = _apply_major_scene_conflict_filters(output, intent)
    output = _apply_explicit_visual_bias_filters(output, user_prompt, source_prompt)
    output = _sanitize_final_canonical_tags(
        output,
        user_prompt,
        source_prompt=source_prompt,
        resolved_tags=resolved_tags,
        copyright_tags=copyright_tags,
        intent=intent,
        subject_count_tags=subject_count_tags,
    )

    composer_meta = {
        "branch": str(intent.get("scene_branch") or "generic").strip().lower() or "generic",
        "facet_counts": _facet_counts(output),
        "variation_seed": prompt_variant_seed if prompt_variant_seed not in (None, "") else hashlib.sha256(
            json.dumps(
                {
                    "user_prompt": user_prompt,
                    "source_prompt": source_prompt,
                    "resolved_tags": resolved_tags,
                    "copyright_tags": copyright_tags,
                    "branch": intent.get("scene_branch"),
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8", "ignore")
        ).hexdigest()[:12],
        "variation_strength": "off" if (strict_prompt_intent or draft_first_prompt_intent) else variation_strength or ("rich" if intent.get("detail_scene") else "balanced" if intent.get("scene_branch") not in {"", "generic", None} else "light"),
        "structured_prompt_intent": structured_prompt_intent,
        "accepted_enrichment_tags": accepted_enrichment_tags,
        "draft_first": draft_first_prompt_intent,
    }
    prompt = _prompt_text_from_tags(
        output,
        user_prompt,
        source_prompt=source_prompt,
        resolved_tags=resolved_tags,
        copyright_tags=copyright_tags,
        variation_strength=composer_meta.get("variation_strength"),
        prompt_variant_seed=prompt_variant_seed,
    )
    return {
        "prompt": prompt,
        "locked": True,
        "intent": intent,
        "resolution": resolution,
        "resolved_tags": resolved_tags,
        "copyright_tags": copyright_tags,
        "scene_tag_count": _scene_tag_count(output),
        "story_facet_counts": _facet_counts(output),
        "prompt_composer": composer_meta,
    }


SUBJECT_COUNT_TAGS = {
    "1girl", "2girls", "3girls", "4girls", "5girls", "6girls",
    "1boy", "2boys", "3boys", "4boys", "5boys", "6boys",
    "multiple_others", "no_humans",
}


def _generic_direct_hint_tags(text):
    output = []
    try:
        direct = canvas_danbooru_service._canvas_danbooru_direct_hint_tags(text)
    except Exception:
        direct = []
    try:
        prompt_hints = canvas_danbooru_service._canvas_danbooru_prompt_hint_tags(text)
    except Exception:
        prompt_hints = []
    for tag in list(direct or []) + list(prompt_hints or []):
        clean = _clean_tag(tag)
        if clean:
            _append_unique(output, [clean])
    return output


def _subject_count_from_candidate_character_tags(candidate_tags):
    girls = 0
    boys = 0
    for tag in dict.fromkeys(candidate_tags or ()):
        hinted = CHARACTER_SUBJECT_COUNT_HINTS.get(tag)
        if hinted == "1girl":
            girls += 1
        elif hinted == "1boy":
            boys += 1
    return _subject_count_tags_from_counts(girls, boys)


def _generic_subject_count_tags(user_prompt, source_prompt, candidate_tags=None, adult_tags=None):
    user_text = str(user_prompt or "").lower()
    source_text = str(source_prompt or "").lower()
    combined = "\n".join(item for item in (user_text, source_text) if item)
    has_passive_external_actor = _has_passive_external_actor_intent(combined)
    has_group_other_people = _has_group_other_people_intent(combined)
    has_external_others = has_passive_external_actor or has_group_other_people

    def with_external_others(tags):
        output = list(tags or [])
        if has_external_others and not set(output).intersection({"1boy", "2boys", "3boys", "4boys", "5boys", "6boys"}):
            _append_unique(output, ["multiple_others"])
        return output

    explicit = _explicit_subject_mention_counts(combined)
    if explicit.get("girls") or explicit.get("boys"):
        output = _subject_count_tags_from_counts(explicit.get("girls"), explicit.get("boys"))
        if output:
            return with_external_others(output)
    candidate_set = set(candidate_tags or [])
    candidate_character_counts = _subject_count_from_candidate_character_tags(candidate_tags or [])
    if candidate_character_counts:
        if len(candidate_character_counts) > 1:
            return with_external_others(candidate_character_counts)
        if candidate_character_counts[0] in {"2girls", "2boys", "3girls", "3boys", "4girls", "4boys", "5girls", "5boys", "6girls", "6boys"}:
            return with_external_others(candidate_character_counts)
    for tag in ("6girls", "5girls", "4girls", "3girls", "2girls", "1girl", "6boys", "5boys", "4boys", "3boys", "2boys", "1boy"):
        if tag in candidate_set:
            return with_external_others([tag])
    if candidate_character_counts:
        return with_external_others(candidate_character_counts)
    if re.search(r"\b(couple|boyfriend|girlfriend)\b|\u60c5\u4fa3|\u4e00\u5bf9|\u4e00\u7537\u4e00\u5973|\u7537\u5973", combined):
        return ["1girl", "1boy"]
    if re.search(r"\u7537\u7c89", combined) and "1girl" in candidate_set:
        return ["1girl", "1boy"]
    if re.search(r"\b(two|2)\s+(?:people|persons|characters|students)\b|\u4e24\s*(?:\u4e2a|\u4f4d|\u540d)?\s*(?:\u4eba|\u89d2\u8272|\u5b66\u751f)", combined):
        if re.search(r"\b(boy|male|man|men)\b|\u7537\u6027|\u7537\u4eba|\u7537\u5b69|\u7537\u751f|\u7537\u89d2\u8272|\u5c11\u5e74|\u7537\u7c89", combined) and "1girl" in candidate_set:
            return ["1girl", "1boy"]
        return ["2girls"]
    if re.search(r"\b(boy|male|man|men)\b|\u7537\u6027|\u7537\u4eba|\u7537\u5b69|\u7537\u751f|\u7537\u89d2\u8272|\u5c11\u5e74|\u7537\u7c89", combined):
        if set(adult_tags or []).intersection(ADULT_PARTNER_REQUIRED_TAGS) or "1girl" in candidate_set:
            return ["1girl", "1boy"]
        return ["1boy"]
    if adult_tags:
        if set(adult_tags or []).intersection(ADULT_PARTNER_REQUIRED_TAGS):
            return ["1girl", "1boy"]
        return with_external_others(["1girl"])
    if re.search(r"\b(girl|female|woman|schoolgirl|student|maid|idol)\b|\u5973\u6027|\u5973\u4eba|\u5973\u5b69|\u5973\u751f|\u5973\u89d2\u8272|\u5c11\u5973|\u7f8e\u5973|\u7f8e\u5c11\u5973|\u5b66\u751f|\u5076\u50cf", combined):
        return with_external_others(["1girl"])
    if candidate_set.intersection({"school_uniform", "idol", "student", "blue_archive"}):
        return with_external_others(["1girl"])
    if has_group_other_people:
        return ["multiple_others"]
    return []


def _is_ambiguous_blue_archive_student_request(user_prompt, source_prompt="", resolution=None):
    if not _blue_archive_student_request_text(user_prompt, source_prompt):
        return False
    resolved = _resolution_tags(resolution or {}, "resolved")
    if not resolved:
        return True
    return set(resolved).issubset({"sensei_(blue_archive)", "doodle_sensei_(blue_archive)"})


def compose_sdxl_generic_prompt(
    user_prompt,
    source_prompt="",
    variation_strength=None,
    prompt_variant_seed=None,
    prompt_intent=None,
    allow_pure_scenery=True,
    allow_named_character_resolution=True,
):
    if allow_pure_scenery:
        pure_scenery = compose_sdxl_pure_scenery_prompt(user_prompt, source_prompt, prompt_intent=prompt_intent)
        if pure_scenery.get("locked"):
            return pure_scenery

    resolution = (
        canvas_danbooru_service._canvas_requested_character_resolution(user_prompt, source_prompt)
        if allow_named_character_resolution
        else {"state": "none", "resolved": [], "candidates": [], "copyright_candidates": []}
    )
    if allow_named_character_resolution and resolution.get("state") == "resolved" and not _is_ambiguous_blue_archive_student_request(user_prompt, source_prompt, resolution):
        return compose_sdxl_named_character_prompt(
            user_prompt,
            source_prompt,
            resolution=resolution,
            variation_strength=variation_strength,
            prompt_variant_seed=prompt_variant_seed,
            prompt_intent=prompt_intent,
        )

    structured_prompt_intent = normalize_structured_prompt_intent(prompt_intent)
    locked_tags = structured_prompt_intent.get("locked_tags") or []
    if _blue_archive_student_request_text(user_prompt, source_prompt):
        locked_tags = [tag for tag in locked_tags if tag != "solo"]
    strict_prompt_intent = structured_prompt_intent_is_strict(structured_prompt_intent)
    draft_first_prompt_intent = bool(
        structured_prompt_intent.get("draft_first")
        or str(structured_prompt_intent.get("scene_strictness") or "") == "draft"
    )
    intent = plan_prompt_intent(user_prompt, source_prompt, resolution=resolution)
    direct_tags = _generic_direct_hint_tags(user_prompt)
    if direct_tags and not allow_named_character_resolution:
        try:
            index = canvas_danbooru_service._canvas_load_danbooru_character_index()
            identity_tags = set(index.get("character_tags") or set()).union(set(index.get("copyright_tags") or set()))
        except Exception:
            identity_tags = set()
        direct_tags = [tag for tag in direct_tags if tag not in identity_tags]
    rule_tags = _rule_tags(user_prompt, GENERIC_PROMPT_RULES)
    adult_intent = detect_adult_intent(user_prompt, source_prompt)
    adult_tags = adult_intent.get("tags") or []
    adult_negative_removed = []
    if adult_tags:
        intent = dict(intent)
        intent["scene_branch"] = "adult"
    has_visual_grounding = bool(
        direct_tags
        or rule_tags
        or locked_tags
        or adult_tags
        or intent.get("scene_tags")
        or intent.get("composition_tags")
        or _has_plain_scene_intent(str(user_prompt or "") + "\n" + str(source_prompt or ""))
    )
    if not has_visual_grounding:
        return {"locked": False, "prompt": "", "intent": intent, "resolution": resolution}

    output = []
    candidate_tags = []
    _append_unique(candidate_tags, direct_tags)
    _append_unique(candidate_tags, rule_tags)
    _append_unique(candidate_tags, locked_tags)
    source_rule_tags = _rule_tags(source_prompt, GENERIC_PROMPT_RULES)
    if adult_tags:
        source_rule_tags = []
    _append_unique(candidate_tags, source_rule_tags)
    subject_count_tags = _generic_subject_count_tags(user_prompt, source_prompt, candidate_tags, adult_tags)
    _append_unique(output, subject_count_tags)
    if (
        subject_count_tags in (["1girl"], ["1boy"])
        and not set(candidate_tags).intersection({"blue_archive"})
        and str(intent.get("scene_branch") or "") not in {"romance", "kiss"}
    ):
        _append_unique(output, ["solo"])

    for tag in candidate_tags:
        if tag in SUBJECT_COUNT_TAGS:
            continue
        _append_unique(output, [tag])

    _append_unique(output, intent.get("composition_tags") or [])
    _append_unique(output, adult_tags)
    _append_unique(output, locked_tags)
    structured_enrichment_tags = list(structured_prompt_intent.get("enrichment_tags") or [])
    accepted_enrichment_tags = structured_enrichment_tags if draft_first_prompt_intent else ([] if strict_prompt_intent else structured_enrichment_tags)
    _append_unique(output, accepted_enrichment_tags)
    _append_unique(output, intent.get("scene_tags") or [])

    if not output:
        return {"locked": False, "prompt": "", "intent": intent, "resolution": resolution}

    branch = str(intent.get("scene_branch") or "").strip().lower()
    if "upper_body" in output:
        output = [tag for tag in output if tag != "full_body"]
    if not intent.get("plain_scene"):
        has_defeated_state = _intent_has_defeated_state(intent)
        profile_tags = []
        if not strict_prompt_intent and not draft_first_prompt_intent and _needs_story_enrichment(output, intent):
            profile_tags = _intent_profile_tags(intent)
        if profile_tags:
            _append_unique(output, profile_tags)
        variant_tags = [] if strict_prompt_intent or draft_first_prompt_intent or has_defeated_state or (branch == "romance" and set(intent.get("scene_tags") or []).intersection(PROFILE_LOCK_TAGS)) else _curated_branch_variant_tags(
            intent,
            user_prompt,
            [],
            [],
            variation_strength=variation_strength,
            variant_seed=prompt_variant_seed,
        )
        _append_unique(output, variant_tags)
        _append_unique(profile_tags, variant_tags)
        if not strict_prompt_intent and not draft_first_prompt_intent and not profile_tags:
            explicit_scene = list(intent.get("scene_tags") or [])
            if explicit_scene:
                fallback = GENERIC_DETAILED_SCENE_TAGS if intent.get("detail_scene") else GENERIC_STANDARD_SCENE_TAGS
                profile_tags = list(explicit_scene) + list(fallback)
        if not strict_prompt_intent:
            if not draft_first_prompt_intent:
                _ensure_story_facets(output, profile_tags, intent)

    if (
        not any(tag in output for tag in ("upper_body", "portrait", "cowboy_shot", "close-up", "full_body", "profile", "from_side"))
        and branch not in {"sleep", "kiss"}
        and "no_humans" not in output
        and not _subject_count_implies_multiple(output)
        and not structured_prompt_intent.get("interaction_focus")
        and not strict_prompt_intent
        and not draft_first_prompt_intent
    ):
        _append_unique(output, ["looking_at_viewer"])

    if set(output).intersection({"1girl", "1boy", "2girls", "2boys", "3girls", "3boys"}):
        output = [tag for tag in output if tag != "no_humans"]
    output = _apply_user_explicit_conflict_filters(output, intent)
    output = _apply_indoor_scene_conflict_filters(output, intent)
    output = _apply_bathing_scene_conflict_filters(output, intent)
    output = _apply_bed_scene_conflict_filters(output, intent)
    output = _apply_beach_scene_conflict_filters(output, intent)
    output = _apply_street_scene_conflict_filters(output, intent)
    output = _apply_adult_conflict_filters(output, adult_tags=adult_tags)
    if adult_tags:
        adult_explicit_tags = []
        _append_unique(adult_explicit_tags, adult_tags)
        _append_unique(adult_explicit_tags, candidate_tags)
        _append_unique(adult_explicit_tags, locked_tags)
        _append_unique(adult_explicit_tags, intent.get("composition_tags") or [])
        _append_unique(adult_explicit_tags, intent.get("scene_tags") or [])
        output, adult_negative_removed = _apply_adult_negative_conflict_filters(
            output,
            adult_tags=adult_tags,
            explicit_tags=adult_explicit_tags,
            preferred_tags=accepted_enrichment_tags,
            return_removed=True,
        )
    output = _apply_major_scene_conflict_filters(output, intent)
    output = _apply_explicit_visual_bias_filters(output, user_prompt, source_prompt)
    _append_unique(output, getattr(canvas_danbooru_policy, "NAMED_CHARACTER_DEFAULT_PROMPT_TAGS", ()))
    output = _apply_indoor_scene_conflict_filters(output, intent)
    output = _apply_bathing_scene_conflict_filters(output, intent)
    output = _apply_bed_scene_conflict_filters(output, intent)
    output = _apply_beach_scene_conflict_filters(output, intent)
    output = _apply_street_scene_conflict_filters(output, intent)
    output = _apply_major_scene_conflict_filters(output, intent)
    output = _apply_explicit_visual_bias_filters(output, user_prompt, source_prompt)
    output = _apply_major_scene_conflict_filters(output, intent)
    output = _sanitize_final_canonical_tags(
        output,
        user_prompt,
        source_prompt=source_prompt,
        resolved_tags=[],
        copyright_tags=[],
        intent=intent,
        subject_count_tags=subject_count_tags,
    )

    composer_meta = {
        "branch": branch or "generic",
        "facet_counts": _facet_counts(output),
        "variation_seed": prompt_variant_seed if prompt_variant_seed not in (None, "") else hashlib.sha256(
            json.dumps(
                {
                    "user_prompt": user_prompt,
                    "source_prompt": source_prompt,
                    "generic_tags": candidate_tags,
                    "branch": intent.get("scene_branch"),
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8", "ignore")
        ).hexdigest()[:12],
        "variation_strength": "off" if (strict_prompt_intent or draft_first_prompt_intent) else variation_strength or ("rich" if intent.get("detail_scene") else "balanced" if branch else "light"),
        "generic": True,
        "structured_prompt_intent": structured_prompt_intent,
        "accepted_enrichment_tags": accepted_enrichment_tags,
        "adult_negative_conflict_removed": adult_negative_removed[:16] if adult_tags else [],
        "draft_first": draft_first_prompt_intent,
    }
    return {
        "prompt": _prompt_text_from_tags(
            output,
            user_prompt,
            source_prompt=source_prompt,
            variation_strength=composer_meta.get("variation_strength"),
            prompt_variant_seed=prompt_variant_seed,
        ),
        "locked": True,
        "intent": intent,
        "resolution": resolution,
        "resolved_tags": [],
        "copyright_tags": [],
        "scene_tag_count": _scene_tag_count(output),
        "story_facet_counts": _facet_counts(output),
        "prompt_composer": composer_meta,
        "generic": True,
    }


def compose_sdxl_pure_scenery_prompt(user_prompt, source_prompt="", prompt_intent=None):
    primary = str(user_prompt or "").strip()
    combined = primary or str(source_prompt or "").strip()
    if not has_pure_scenery_intent(combined):
        return {"locked": False, "prompt": ""}
    structured_prompt_intent = normalize_structured_prompt_intent(prompt_intent)
    output = []
    _append_unique(output, ["scenery", "landscape", "no_humans"])
    _append_unique(output, _rule_tags(user_prompt, SCENE_RULES))
    _append_unique(output, _rule_tags(source_prompt, SCENE_RULES))
    _append_unique(output, structured_prompt_intent.get("locked_tags") or [])
    _append_unique(output, structured_prompt_intent.get("enrichment_tags") or [])
    if _scene_tag_count(output) < 3:
        _append_unique(output, ("outdoors", "wide_shot", "depth_of_field"))
    if "depth_of_field" not in output and "wide_shot" not in output:
        _append_unique(output, ["depth_of_field"])
    output = _apply_explicit_visual_bias_filters(output, user_prompt, source_prompt)
    output = _sanitize_final_canonical_tags(output, user_prompt, source_prompt=source_prompt, intent={"scene_tags": output})
    return {
        "locked": True,
        "prompt": _prompt_text_from_tags(output, user_prompt, source_prompt=source_prompt, variation_strength="light"),
        "scene_tag_count": _scene_tag_count(output),
    }


def build_locked_prompt_context(user_prompt, source_prompt=""):
    result = compose_sdxl_named_character_prompt(user_prompt, source_prompt)
    if not result.get("locked"):
        result = compose_sdxl_generic_prompt(user_prompt, source_prompt)
    if not result.get("locked"):
        return {}
    context = {
        "state": "locked_named_character_prompt_plan",
        "planner": result.get("intent") or {},
        "scene_branch_options": SCENE_BRANCH_SUMMARY,
        "resolver": {
            "character_tags": result.get("resolved_tags") or [],
            "copyright_tags": result.get("copyright_tags") or [],
        },
        "composer": {
            "recommended_prompt": result.get("prompt") or "",
            "scene_tag_count": result.get("scene_tag_count", 0),
            "story_facet_counts": result.get("story_facet_counts") or {},
        },
        "tag_pool": "Scene variants are sampled from tags/weilin_tagcart.csv when a branch has safe curated slot candidates.",
        "rule": "Use canonical character/copyright tags as locked facts. Expand scene, action, camera, lighting, and atmosphere instead of restating default hair, eye, outfit, or assistant persona traits.",
    }
    return context


def locked_prompt_context_text(user_prompt, source_prompt="", max_chars=2500):
    context = build_locked_prompt_context(user_prompt, source_prompt)
    if not context:
        return ""
    text = json.dumps(context, ensure_ascii=False, indent=2)
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n..."
    return text
