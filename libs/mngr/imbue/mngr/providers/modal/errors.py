from imbue.mngr.errors import MngrError


class ModalMngrError(MngrError):
    pass


class NoSnapshotsModalMngrError(ModalMngrError):
    pass
