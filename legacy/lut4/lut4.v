module top();
  wire gen_000_;
  wire gen_001_;
  wire gen_002_;
  wire gen_003_;
  wire gen_004_;
  wire gen_005_;
  wire gen_006_;
  wire gen_007_;
  wire gen_008_;
  wire gen_009_;
  wire gen_010_;
  wire gen_011_;
  LUT4 mylut (
    .F(gen_000_),
    .I0(gen_001_),
    .I1(gen_002_),
    .I2(gen_003_),
    .I3(gen_004_ )
  );
  defparam mylut.INIT = 16'h0000;
  LUT4 mylut2 (
    .F(gen_005_),
    .I0(gen_000_),
    .I1(gen_007_),
    .I2(gen_008_),
    .I3(gen_009_ )
  );
  /*defparam mylut2.INIT = 16'haaaa;
  DFFE mydff (
    .CE(gen_010_),
    .CLK(gen_011_),
    .D(gen_000_),
    .Q(gen_006_)
  );*/
endmodule
