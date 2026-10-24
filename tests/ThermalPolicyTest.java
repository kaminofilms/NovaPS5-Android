package com.kaminofilms.novaps5;
public class ThermalPolicyTest {
 static void check(boolean ok){if(!ok)throw new AssertionError();}
 public static void main(String[] args){
  ThermalPolicy p=new ThermalPolicy();check(p.update(0,0,0,.2f)==0);
  check(p.update(10000,0,2,.9f)==1);check(p.update(20000,0,3,1.1f)==2);
  for(long t=30000;t<90000;t+=10000)check(p.update(t,0,0,.3f)==2);
  check(p.update(90000,0,0,.3f)==1);check(p.update(100000,0,0,.3f)==1);check(p.update(120000,0,0,.3f)==0);
  check(p.update(130000,1,0,.2f)==1);check(p.update(240000,1,0,.2f)==1);
  p=new ThermalPolicy();check(p.update(0,2,0,.9f)==0);check(p.update(10000,2,3,Float.NaN)==2);
  check(p.update(999999,2,-1,Float.NaN)==2); // no recovery without sensor evidence
  p=new ThermalPolicy();for(long t=0;t<1000000;t+=10000){p.update(t,0,0,.86f);check(p.update(t+5000,0,0,.7f)==1);}
  System.out.println("PASS thermal escalation, hysteresis, gradual recovery, unavailable sensors, Cooler floor, oscillation");
 }
}
