class InventoryLineBuilder:
    def skipped_or_empty_configurations(self):
        return ["# ignore", "     #", "", "      "]

    def valid_inventory_lines(self):
        return [
            "127.0.0.1, 2c ,public,router,1",
            "127.0.0.1:6666, 2c,public,router,1",
            "127.0.0.1,3 ,public,router,1",
            "127.0.0.1:6666,3,public,router,1",
            "localhost,2c,public,router,1",
            "localhost:6666,2c,public,router,1",
            "localhost,3,public,router,1",
            "localhost:6666,3,public,router,1",
        ]

    def invalid_host_names(self):
        # This is a list of tests where we have either invalid hostnames/domains and/or
        # invalid ports. The format of each entry is:
        # hostname|IP<:port>, where
        return [
            ":,2c,public,router,1",
            "127.0.0.1:,2c,public,router,1",
            ":123,2c,public,router,1",
            "WE.SHOULD.NOT.RESOLVE.THIS.GUY:123,2c,public,router,1",
            "127.0.0.1:76666,2c,public,router,1",
            "127.0.0.1:-166,2c,public,router,1",
            "127.0.0.1:NotANumber,2c,public,router,1",
        ]

    def invalid_snmp_versions(self):
        # Right now we support only version "2c" and "3"
        return [
            "127.0.0.1, 2cc ,public,router,1",
            "127.0.0.1, 4 ,public,router,1",
        ]

    def invalid_communities(self):
        # For now we support only public
        return [
            "127.0.0.1, 2cc ,public_invalid,router,1",
        ]
