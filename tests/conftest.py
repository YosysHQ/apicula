def pytest_addoption(parser):
    group = parser.getgroup('fuzz', 'tiled fuzzer (tests/test_fuzz.py); needs GOWINHOME and the device chipdb')
    group.addoption('--device', action='append', default=[], help='device to fuzz; repeat for several')
    group.addoption('--fuzz-count', type=int, default=2, help='cases per primitive')
    group.addoption('--fuzz-seed', type=int, default=7)
    group.addoption('--fuzz-jobs', type=int, default=1, help='designs run at the same time')
    group.addoption('--fuzz-out', default='fuzz-out', help='directory for the reports')
