def foo():
    assert 1 == 1
    # adding a new assert - will be rewritten to pytest assert
    x = 2
    assert 1 == x
