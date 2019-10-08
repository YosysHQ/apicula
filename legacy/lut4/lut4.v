module top();
  wire gen_000_;
  wire gen_001_;
  wire gen_002_;
  wire gen_003_;
  wire gen_004_;
  LUT4 mylut (
    .F(gen_000_),
    .I0(gen_001_),
    .I1(gen_002_),
    .I2(gen_003_),
    .I3(gen_004_ )
  );
  defparam mylut.INIT = 16'h0000;
endmodule
