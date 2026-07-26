def distribute_phone(phone_count, word_count):
    phones_per_word = [0] * word_count
    for _ in range(phone_count):
        minimum = min(phones_per_word)
        index = phones_per_word.index(minimum)
        phones_per_word[index] += 1
    return phones_per_word
