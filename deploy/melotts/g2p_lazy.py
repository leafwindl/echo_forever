class LazyG2p:
    def __init__(self):
        self._delegate = None

    def __call__(self, text):
        if self._delegate is None:
            from g2p_en import G2p

            self._delegate = G2p()
        return self._delegate(text)
