import importlib

from .symbols import *


_symbol_to_id = {symbol: index for index, symbol in enumerate(symbols)}


def cleaned_text_to_sequence(cleaned_text, tones, language, symbol_to_id=None):
    symbol_to_id_map = symbol_to_id if symbol_to_id else _symbol_to_id
    phones = [symbol_to_id_map[symbol] for symbol in cleaned_text]
    tone_start = language_tone_start_map[language]
    tones = [tone + tone_start for tone in tones]
    language_id = language_id_map[language]
    language_ids = [language_id for _ in phones]
    return phones, tones, language_ids


def get_bert(norm_text, word2ph, language, device):
    module_names = {
        "ZH": "chinese_bert",
        "EN": "english_bert",
        "JP": "japanese_bert",
        "ZH_MIX_EN": "chinese_mix",
        "FR": "french_bert",
        "SP": "spanish_bert",
        "ES": "spanish_bert",
        "KR": "korean",
    }
    module = importlib.import_module(f"{__package__}.{module_names[language]}")
    return module.get_bert_feature(norm_text, word2ph, device)
