// main.cpp - gowin_pack C++ implementation entry point
#include <CLI/CLI.hpp>
#include <iostream>
#include <fstream>
#include <string>
#include <regex>

#include "chipdb.hpp"
#include "netlist.hpp"
#include "bitstream.hpp"

int main(int argc, char** argv) {
    CLI::App app{"gowin_pack - Bitstream packer for Gowin FPGAs"};

    std::string device;
    std::string input_file;
    std::string output_file;
    std::string chipdb_path;
    std::string cst_file;
    bool compress = false;
    bool jtag_as_gpio = false;
    bool sspi_as_gpio = false;
    bool mspi_as_gpio = false;
    bool ready_as_gpio = false;
    bool done_as_gpio = false;
    bool reconfign_as_gpio = false;
    bool cpu_as_gpio = false;
    bool i2c_as_gpio = false;

    app.add_option("-d,--device", device, "Device name (e.g., GW1N-9C)")
        ->required();
    app.add_option("-o,--output", output_file, "Output bitstream file (.fs)")
        ->required();
    app.add_option("input", input_file, "Input Nextpnr JSON file")
        ->required();
    app.add_option("--chipdb", chipdb_path, "Path to chipdb file (optional)");
    app.add_option("-s,--cst", cst_file, "Output constraints file");
    app.add_flag("-c,--compress", compress, "Compress output bitstream");
    app.add_flag("--jtag_as_gpio", jtag_as_gpio, "Use JTAG pins as GPIO");
    app.add_flag("--sspi_as_gpio", sspi_as_gpio, "Use SSPI pins as GPIO");
    app.add_flag("--mspi_as_gpio", mspi_as_gpio, "Use MSPI pins as GPIO");
    app.add_flag("--ready_as_gpio", ready_as_gpio, "Use READY pin as GPIO");
    app.add_flag("--done_as_gpio", done_as_gpio, "Use DONE pin as GPIO");
    app.add_flag("--reconfign_as_gpio", reconfign_as_gpio, "Use RECONFIGN pin as GPIO");
    app.add_flag("--cpu_as_gpio", cpu_as_gpio, "Use CPU pins as GPIO");
    app.add_flag("--i2c_as_gpio", i2c_as_gpio, "Use I2C pins as GPIO");

    CLI11_PARSE(app, argc, argv);

    try {
        // Parse device from full part number if provided
        std::regex part_re(R"((GW..)(S|Z)?[A-Z]*-(LV|UV|UX)([0-9]{1,2})C?([A-Z]{2}[0-9]+P?)(C[0-9]/I[0-9]))");
        std::smatch match;
        if (std::regex_match(device, match, part_re)) {
            std::string series = match[1].str();
            std::string mods = match[2].str();
            std::string num = match[4].str();
            device = series + mods + "-" + num;
        }

        // Load chip database
        std::cout << "Loading chipdb for " << device << "..." << std::endl;
        auto db = apycula::load_chipdb(chipdb_path.empty()
            ? apycula::find_chipdb(device)
            : chipdb_path);

        std::cout << "Device grid: " << db.rows() << "x" << db.cols() << std::endl;

        // Parse netlist
        std::cout << "Parsing netlist from " << input_file << "..." << std::endl;
        auto netlist = apycula::parse_netlist(input_file);

        // Check for himbaechel arch
        auto arch_it = netlist.settings.find("packer.arch");
        if (arch_it == netlist.settings.end() || arch_it->second != "himbaechel/gowin") {
            std::cerr << "Error: Only files made with nextpnr-himbaechel are supported." << std::endl;
            return 1;
        }

        // Generate bitstream
        std::cout << "Generating bitstream..." << std::endl;
        apycula::PackArgs pack_args;
        pack_args.device = device;
        pack_args.compress = compress;
        pack_args.jtag_as_gpio = jtag_as_gpio;
        pack_args.sspi_as_gpio = sspi_as_gpio;
        pack_args.mspi_as_gpio = mspi_as_gpio;
        pack_args.ready_as_gpio = ready_as_gpio;
        pack_args.done_as_gpio = done_as_gpio;
        pack_args.reconfign_as_gpio = reconfign_as_gpio;
        pack_args.cpu_as_gpio = cpu_as_gpio;
        pack_args.i2c_as_gpio = i2c_as_gpio;
        auto bitstream = apycula::generate_bitstream(db, netlist, pack_args);

        // Write output
        std::cout << "Writing output to " << output_file << "..." << std::endl;
        apycula::write_bitstream(output_file, bitstream);

        std::cout << "Done." << std::endl;
        return 0;

    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << std::endl;
        return 1;
    }
}
