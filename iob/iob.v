module top(outp);
  output outp;
  wire gen_000_;
  OBUF myobuf (
    .I(gen_000_),
    .O(outp)
  );
endmodule
