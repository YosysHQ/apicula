// Applies Gowin annotations to libgowin.so and decompiles selected functions.
// Run through tools/gowin_decompile.py, which writes the annotation JSON.
import com.google.gson.*;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.decompiler.*;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.data.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.SourceType;
import java.nio.file.*;
import java.util.*;

public class GowinDecompile extends GhidraScript {
    private final Map<String, DataType> types = new HashMap<>();
    private long base;

    private Address addr(long offset) {
        return toAddr(base + offset);
    }

    private DataType type(String name) {
        if (name.endsWith("*")) return new PointerDataType(type(name.substring(0, name.length() - 1)));
        switch (name) {
            case "void": return VoidDataType.dataType;
            case "short": return ShortDataType.dataType;
            case "int": return IntegerDataType.dataType;
            case "char": return CharDataType.dataType;
            case "bool": return BooleanDataType.dataType;
            default: break;
        }
        DataType known = types.get(name);
        if (known == null) throw new IllegalArgumentException("unknown type " + name);
        return known;
    }

    private void defineTypes(JsonObject config) {
        DataTypeManager manager = currentProgram.getDataTypeManager();
        CategoryPath category = new CategoryPath("/gowin");
        for (Map.Entry<String, JsonElement> e : config.getAsJsonObject("enums").entrySet()) {
            EnumDataType en = new EnumDataType(category, e.getKey(), 4);
            for (Map.Entry<String, JsonElement> v : e.getValue().getAsJsonObject().entrySet()) {
                en.add(v.getValue().getAsString(), Long.parseLong(v.getKey()));
            }
            types.put(e.getKey(), manager.addDataType(en, DataTypeConflictHandler.REPLACE_HANDLER));
        }
        for (Map.Entry<String, JsonElement> e : config.getAsJsonObject("structs").entrySet()) {
            JsonObject spec = e.getValue().getAsJsonObject();
            StructureDataType struct = new StructureDataType(category, e.getKey(), spec.get("size").getAsInt());
            DataType field = new PointerDataType(CharDataType.dataType);
            for (Map.Entry<String, JsonElement> f : spec.getAsJsonObject("fields").entrySet()) {
                struct.replaceAtOffset(Integer.parseInt(f.getKey()), field, 8, f.getValue().getAsString(), null);
            }
            types.put(e.getKey(), manager.addDataType(struct, DataTypeConflictHandler.REPLACE_HANDLER));
        }
    }

    private Function define(long offset, long size, String name) throws Exception {
        Address start = addr(offset);
        AddressSet body = new AddressSet(start, start.add(Math.max(size, 1) - 1));
        Address cursor = start;
        while (body.contains(cursor)) {
            Instruction insn = getInstructionAt(cursor);
            if (insn == null) {
                new DisassembleCommand(cursor, body, true).applyTo(currentProgram, monitor);
                insn = getInstructionAt(cursor);
            }
            if (insn == null) {
                cursor = cursor.add(1);
            } else {
                cursor = cursor.add(insn.getLength());
            }
        }
        Function f = getFunctionAt(start);
        if (f == null) f = createFunction(start, name);
        if (f == null) throw new IllegalStateException("cannot create function " + name);
        f.setName(name, SourceType.USER_DEFINED);
        if (size > 1) f.setBody(body);
        return f;
    }

    private void applySignature(Function f, JsonObject sig) throws Exception {
        List<ParameterImpl> params = new ArrayList<>();
        for (JsonElement p : sig.getAsJsonArray("params")) {
            JsonArray pair = p.getAsJsonArray();
            params.add(new ParameterImpl(pair.get(0).getAsString(), type(pair.get(1).getAsString()), currentProgram));
        }
        f.replaceParameters(Function.FunctionUpdateType.DYNAMIC_STORAGE_ALL_PARAMS, true,
                SourceType.USER_DEFINED, params.toArray(new ParameterImpl[0]));
        if (sig.has("returns")) f.setReturnType(type(sig.get("returns").getAsString()), SourceType.USER_DEFINED);
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        JsonObject config = JsonParser.parseString(Files.readString(Path.of(args[0]))).getAsJsonObject();
        Path out = Path.of(args[1]);
        Files.createDirectories(out);
        base = currentProgram.getImageBase().getOffset();
        defineTypes(config);

        for (JsonElement e : config.getAsJsonArray("callees")) {
            JsonObject callee = e.getAsJsonObject();
            Function f = define(callee.get("address").getAsLong(), 0, callee.get("name").getAsString());
            if (callee.has("signature")) applySignature(f, callee.getAsJsonObject("signature"));
        }

        for (JsonElement e : config.getAsJsonArray("strings")) {
            Address at = addr(e.getAsLong());
            if (getDataAt(at) == null) {
                try {
                    createAsciiString(at);
                } catch (Exception ignored) {
                    // overlapping data: leave it as an address
                }
            }
        }

        DecompInterface decompiler = new DecompInterface();
        DecompileOptions options = new DecompileOptions();
        options.setMaxPayloadMBytes(200);
        decompiler.setOptions(options);
        decompiler.openProgram(currentProgram);
        for (JsonElement e : config.getAsJsonArray("targets")) {
            JsonObject target = e.getAsJsonObject();
            String name = target.get("name").getAsString();
            Function f = define(target.get("address").getAsLong(), target.get("size").getAsLong(), name);
            DecompileResults result = decompiler.decompileFunction(f, 600, monitor);
            String text = result.decompileCompleted() ? result.getDecompiledFunction().getC()
                    : "// decompilation failed: " + result.getErrorMessage() + "\n";
            Files.writeString(out.resolve(target.get("file").getAsString()), text);
            println("wrote " + target.get("file").getAsString() + " (" + text.length() + " chars)");
        }
        decompiler.dispose();
    }
}
