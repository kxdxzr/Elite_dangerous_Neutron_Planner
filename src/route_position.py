"""Match confirmed positions against canonical route order, never table sorting."""


class RoutePosition:
    def __init__(self):
        self.set_route([])

    def set_route(self, rows):
        self.names = tuple(row['name'] for row in rows)
        self.positions = {}
        for index, name in enumerate(self.names):
            self.positions.setdefault(name.casefold(), []).append(index)
        self.index = None
        self.ambiguous = False
        self.copied = set()
        self.evidence = None

    def match(self, system, evidence=None):
        matches = self.positions.get(system.strip().casefold(), []) if system else []
        previous_evidence, self.evidence = self.evidence, evidence
        self.ambiguous = False
        if len(matches) == 1:
            self.index = matches[0]
        elif matches and self.index in matches:
            # A *new* record at a repeated system might follow missed travel or
            # a session change. Do not pretend it is still the same occurrence.
            if evidence is not None and previous_evidence is not None and evidence != previous_evidence:
                self.index, self.ambiguous = None, True
        elif matches and self.index is not None and self.index + 1 in matches:
            self.index += 1
        else:
            self.index = None
            self.ambiguous = bool(matches)
        return self.index

    def choose(self, index, system):
        if index in self.positions.get(system.strip().casefold(), []):
            self.index, self.ambiguous = index, False
            return True
        return False

    @property
    def next_system(self):
        if self.index is not None and self.index + 1 < len(self.names):
            return self.names[self.index + 1]
        return None

    @property
    def should_copy(self):
        name = self.next_system
        return (name is not None and self.index not in self.copied and 0 < len(name) <= 256
                and not any(ord(c) < 32 for c in name))

    def mark_copied(self):
        if self.index is not None:
            self.copied.add(self.index)
