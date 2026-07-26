import copy
import importlib

from . import cleaned_text_to_sequence


LANGUAGE_MODULES = {
    "ZH": "chinese",
    "JP": "japanese",
    "EN": "english",
    "ZH_MIX_EN": "chinese_mix",
    "KR": "korean",
    "FR": "french",
    "SP": "spanish",
    "ES": "spanish",
}


def _language_module(language):
    module_name = LANGUAGE_MODULES[language]
    return importlib.import_module(f"{__package__}.{module_name}")


def clean_text(text, language):
    language_module = _language_module(language)
    norm_text = language_module.text_normalize(text)
    phones, tones, word2ph = language_module.g2p(norm_text)
    return norm_text, phones, tones, word2ph


def clean_text_bert(text, language, device=None):
    language_module = _language_module(language)
    norm_text = language_module.text_normalize(text)
    phones, tones, word2ph = language_module.g2p(norm_text)

    original_word2ph = copy.deepcopy(word2ph)
    for index in range(len(word2ph)):
        word2ph[index] *= 2
    word2ph[0] += 1
    bert = language_module.get_bert_feature(norm_text, word2ph, device=device)
    return norm_text, phones, tones, original_word2ph, bert


def text_to_sequence(text, language):
    _, phones, tones, _ = clean_text(text, language)
    return cleaned_text_to_sequence(phones, tones, language)
