
class SQL:
    def __init__(self, host, port, user, password, database):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database


sql_mc = SQL("88.99.61.194", 3306,
          "u8_AEZRh5Wfhn", "KBNVzuOsC+0TIQC!e!2O4fxe",
          "s8_Activity")
TOKEN = ${{ secrets.TOKEN }}
